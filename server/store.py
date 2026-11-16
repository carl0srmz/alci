import json, sqlite3, threading, time
import config

_db = sqlite3.connect(config.DATA / "alci.db", check_same_thread=False)
_db.row_factory = sqlite3.Row
_lock = threading.Lock()
_db.executescript("""
CREATE TABLE IF NOT EXISTS m(id INTEGER PRIMARY KEY, ts INTEGER, ph REAL, ph_v REAL, ph_cal INTEGER,
  ntu REAL, turb_v REAL, temp REAL, score INTEGER, parts TEXT);
CREATE TABLE IF NOT EXISTS a(mid INTEGER PRIMARY KEY, ts INTEGER, body TEXT);
CREATE INDEX IF NOT EXISTS m_ts ON m(ts);
""")

def add_measurement(r, score, parts):
    with _lock:
        c = _db.execute("INSERT INTO m(ts,ph,ph_v,ph_cal,ntu,turb_v,temp,score,parts) VALUES(?,?,?,?,?,?,?,?,?)",
                        (int(time.time()), r.get("ph"), r.get("ph_v"), int(bool(r.get("ph_calibrated"))),
                         r.get("turb_ntu"), r.get("turb_v"), r.get("temp_c"), score, json.dumps(parts)))
        _db.commit()
        return c.lastrowid

def add_analysis(mid, body):
    with _lock:
        _db.execute("INSERT OR REPLACE INTO a VALUES(?,?,?)", (mid, int(time.time()), json.dumps(body)))
        _db.commit()

def clear():
    with _lock:
        _db.execute("DELETE FROM a"); _db.execute("DELETE FROM m"); _db.commit()

def _m(row):
    d = dict(row)
    d["parts"] = json.loads(d["parts"])
    return d

def latest():
    with _lock:
        r = _db.execute("SELECT * FROM m ORDER BY ts DESC LIMIT 1").fetchone()
        if not r:
            return None
        a = _db.execute("SELECT body,ts FROM a WHERE mid=?", (r["id"],)).fetchone()
    d = _m(r)
    d["analysis"] = json.loads(a["body"]) if a else None
    return d

def history(days):
    with _lock:
        rows = _db.execute("SELECT * FROM m WHERE ts>? ORDER BY ts", (time.time() - days * 86400,)).fetchall()
    return [_m(r) for r in rows]

def recent_analyses(n=10):
    with _lock:
        rows = _db.execute("SELECT m.id,m.ts,m.score,a.body FROM a JOIN m ON m.id=a.mid ORDER BY m.ts DESC LIMIT ?", (n,)).fetchall()
    return [{"id": r["id"], "ts": r["ts"], "score": r["score"], "analysis": json.loads(r["body"])} for r in rows]
