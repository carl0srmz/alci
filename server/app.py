import hmac, os, re, secrets, shutil, subprocess, threading, time
from pathlib import Path
import requests
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import analysis, config, redirect, sensors, store

STATIC = config.ROOT / "static"
app = FastAPI(title="ALCI")
NAME = config.device_name()

# ---- admin auth: public dashboard is read-only; anything that acts needs the password ----
_pw_file = config.DATA / "ADMIN_PASSWORD.txt"
if not _pw_file.exists():
    _pw_file.write_text(secrets.token_urlsafe(9))
    _pw_file.chmod(0o600)
PASSWORD = _pw_file.read_text().strip()
_sessions = set()  # shortcut: in memory, a restart logs admins out

def admin(alci_session: str | None = Cookie(None)):
    if alci_session not in _sessions:
        raise HTTPException(401, "Inicia sesión como administrador.")

@app.post("/api/login")
def login(body: dict, request: Request, response: Response):
    if not hmac.compare_digest(str(body.get("password", "")), PASSWORD):
        time.sleep(1)
        raise HTTPException(403, "Contraseña incorrecta.")
    t = secrets.token_urlsafe(24)
    _sessions.add(t)
    response.set_cookie("alci_session", t, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=30 * 86400)
    return {"ok": True}

@app.post("/api/logout")
def logout(response: Response, alci_session: str | None = Cookie(None)):
    _sessions.discard(alci_session)
    response.delete_cookie("alci_session")
    return {"ok": True}

# ---- background jobs ----
jobs = {}
_job_lock = threading.Lock()

def start_job(name, fn):
    with _job_lock:
        if jobs.get(name, {}).get("state") == "running":
            raise HTTPException(409, "Ya hay una tarea igual en curso.")
        jobs[name] = {"state": "running", "log": "", "started": int(time.time())}
    def run():
        try:
            jobs[name]["log"] = fn(lambda s: jobs[name].__setitem__("log", jobs[name]["log"] + s)) or jobs[name]["log"]
            jobs[name]["state"] = "done"
        except Exception as e:
            jobs[name].update(state="error", log=jobs[name]["log"] + f"\n{e}")
    threading.Thread(target=run, daemon=True).start()

def cycle(log=lambda s: None):
    log("Llenando contenedor…\n")
    try:
        sensors.fill_sample()
        log("Midiendo…\n")
        r = sensors.measure()
    finally:
        sensors.drain_sample()
    sc, parts = analysis.score(r)
    if sc is None:
        raise RuntimeError("; ".join(r["errors"]) or "sin lecturas")
    mid = store.add_measurement(r, sc, parts)
    log("Analizando con el modelo local (puede tardar unos minutos)…\n")
    rec = analysis.patterns(store.history(30))
    store.add_analysis(mid, analysis.analyze(r, sc, parts, rec))
    log("Listo.\n")

@app.on_event("startup")
def _scheduler():
    def loop():
        while True:
            if not config.settings["auto"]:
                time.sleep(30)
                continue
            last = store.latest()
            wait = config.settings["interval_min"] * 60 - (time.time() - last["ts"] if last else 1e9)
            time.sleep(max(30, min(wait, 600)) if wait > 0 else 0)
            last = store.latest()
            if not last or time.time() - last["ts"] >= config.settings["interval_min"] * 60:
                try:
                    start_job("measure", cycle)
                except HTTPException:
                    pass
                time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()

    def sync_redirect():  # keeps the InfinityFree redirector pointing at the live tunnel URL
        while True:
            u = tunnel_url()
            if u and u != redirect.last_url and redirect.creds():
                try:
                    redirect.publish(u)
                except Exception as e:
                    print("redirect:", e, flush=True)
            time.sleep(60)
    threading.Thread(target=sync_redirect, daemon=True).start()

# ---- tunnel url (cloudflared logs it) ----
def tunnel_url():
    try:
        m = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", (config.DATA / "tunnel.log").read_text())
        named = config._load("tunnel.json", None)
        return f"https://{named['hostname']}" if named else (m[-1] if m else None)
    except Exception:
        return None

# ---- read API (public) ----
@app.get("/api/status")
def status(alci_session: str | None = Cookie(None)):
    try:
        ollama_ok = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=2).ok
    except Exception:
        ollama_ok = False
    cal = sensors._cal()
    return {"device": NAME, "domain": f"{NAME}.{config.DOMAIN}", "url": tunnel_url(), "now": int(time.time()),
            "admin": alci_session in _sessions, "latest": store.latest(), "ollama": ollama_ok, "model": config.MODEL,
            "redirect": {"ok": redirect.last_url is not None, "error": redirect.last_error}, "pumps": bool(config.PUMPS_ENABLED), "interval_min": config.settings["interval_min"], "auto": config.settings["auto"],
            "calibration": cal and {k: cal[k] for k in ("ts", "max_err")},
            "turb_calibration": config._load("calibration_turb.json", None), "jobs": jobs}

@app.get("/api/history")
def history(days: int = 7):
    days = max(1, min(days, 365))
    rows = store.history(days)
    return {"rows": rows, "patterns": analysis.patterns(rows)}

@app.get("/api/advice")
def advice():
    return store.recent_analyses(10)

@app.get("/api/live")
def live():
    return sensors.measure()

# ---- admin API ----
@app.post("/api/measure", dependencies=[Depends(admin)])
def measure_now():
    start_job("measure", cycle)
    return {"ok": True}

@app.put("/api/settings", dependencies=[Depends(admin)])
def put_settings(body: dict):
    if "interval_min" in body:
        config.settings["interval_min"] = max(5, min(int(body["interval_min"]), 7 * 1440))
    if "auto" in body:
        config.settings["auto"] = bool(body["auto"])
    config.save_settings()
    return config.settings

_cal_points = []

@app.post("/api/calibrate/ph/capture", dependencies=[Depends(admin)])
def cal_capture(body: dict):
    b = float(body["buffer"])
    if b not in (4.0, 6.86, 9.18):
        raise HTTPException(400, "Solución no válida.")
    try:
        p = sensors.capture_buffer(b)
    except ValueError as e:
        raise HTTPException(422, str(e))
    _cal_points[:] = [q for q in _cal_points if q["buffer"] != b] + [p]
    return {"points": _cal_points}

@app.post("/api/calibrate/ph/commit", dependencies=[Depends(admin)])
def cal_commit():
    try:
        cal = sensors.fit_calibration(list(_cal_points))
    except ValueError as e:
        raise HTTPException(422, str(e))
    _cal_points.clear()
    return cal

@app.post("/api/calibrate/ph/reset", dependencies=[Depends(admin)])
def cal_reset():
    _cal_points.clear()
    (config.DATA / "calibration.json").unlink(missing_ok=True)
    return {"ok": True}

@app.post("/api/calibrate/turb/capture", dependencies=[Depends(admin)])
def turb_capture():
    try:
        return sensors.capture_clear_water()
    except ValueError as e:
        raise HTTPException(422, str(e))

@app.post("/api/calibrate/turb/reset", dependencies=[Depends(admin)])
def turb_reset():
    (config.DATA / "calibration_turb.json").unlink(missing_ok=True)
    return {"ok": True}

@app.get("/api/system", dependencies=[Depends(admin)])
def system():
    du = shutil.disk_usage("/")
    cpu = Path("/sys/class/thermal/thermal_zone0/temp").read_text()
    return {"uptime_s": float(Path("/proc/uptime").read_text().split()[0]), "cpu_c": int(cpu) / 1000,
            "disk_free_gb": du.free / 1e9, "disk_total_gb": du.total / 1e9,
            "mem": {l.split(":")[0]: int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()[:3]},
            "last_update": config._load("last_update.json", None)}

def _update(log):
    p = subprocess.run(["sudo", "-n", "/usr/local/sbin/alci-update"], capture_output=True, text=True, timeout=3600)
    out = (p.stdout + p.stderr)[-4000:]
    config._save("last_update.json", {"ts": int(time.time()), "ok": p.returncode == 0})
    if p.returncode:
        raise RuntimeError(out)
    return out

@app.post("/api/system/update", dependencies=[Depends(admin)])
def system_update():
    start_job("update", _update)
    return {"ok": True}

@app.post("/api/system/reboot", dependencies=[Depends(admin)])
def reboot():
    subprocess.Popen(["sudo", "-n", "/usr/sbin/reboot"])
    return {"ok": True}

# ---- pages ----
MOBILE = re.compile(r"Mobi|Android|iPhone|iPad", re.I)

@app.get("/")
def index(request: Request, view: str | None = None):
    mobile = view == "mobile" or (view != "desktop" and MOBILE.search(request.headers.get("user-agent", "")))
    return FileResponse(STATIC / ("mobile.html" if mobile else "desktop.html"), headers={"Cache-Control": "no-cache"})

app.mount("/static", StaticFiles(directory=STATIC), name="static")

if __name__ == "__main__":
    import uvicorn
    print(f"ALCI '{NAME}' en puerto {config.PORT}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, proxy_headers=True, forwarded_allow_ips="127.0.0.1")
