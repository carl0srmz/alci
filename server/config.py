import json, os, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

def _env(k, d):
    return type(d)(os.environ.get(k, d))

PORT = _env("ALCI_PORT", 8080)
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = _env("ALCI_MODEL", "qwen3.5:4b")
DOMAIN = _env("ALCI_DOMAIN", "alci.xxxx")  # shortcut: placeholder until a real domain is owned

# ADS1115 channels + divider ratios (both are 10k/10k = 2.0) (Vsensor = Vadc * scale). The ADS runs at 3.3 V,
# so 5 V sensors MUST go through a divider; set the real ratio here.
PH_CH = _env("ALCI_PH_CH", 1)
TURB_CH = _env("ALCI_TURB_CH", 0)
PH_SCALE = _env("ALCI_PH_SCALE", 2.0)
TURB_SCALE = _env("ALCI_TURB_SCALE", 2.0)

# Pumps (R385 via MOSFET/relay driver). Off until wired.
def _flag(k, d):
    return os.environ.get(k, str(d)).strip().lower() in ("1", "true", "yes", "on")

PUMPS_ENABLED = _flag("ALCI_PUMPS", 0)
PUMP_IN_PIN = _env("ALCI_PUMP_IN_PIN", 17)
PUMP_OUT_PIN = _env("ALCI_PUMP_OUT_PIN", 27)
PUMP_ACTIVE_LOW = _flag("ALCI_PUMP_ACTIVE_LOW", 1)  # most relay modules switch ON when the pin goes LOW
PUMP_SERIAL = os.environ.get("ALCI_PUMP_SERIAL", "")  # e.g. /dev/ttyUSB0: relays driven by an Arduino instead of GPIO
FILL_S, SETTLE_S, DRAIN_S = _env("ALCI_FILL_S", 40), _env("ALCI_SETTLE_S", 20), _env("ALCI_DRAIN_S", 45)

def _load(name, default):
    p = DATA / name
    try:
        return json.loads(p.read_text())
    except Exception:
        return default

def _save(name, obj):
    (DATA / name).write_text(json.dumps(obj))

def device_name():
    d = _load("device.json", None)
    if not d:
        r = random.SystemRandom()
        d = {"name": "-".join([r.choice(["gota", "rio", "lago", "pozo", "fuente", "laguna", "nube"]),
                               r.choice(["clara", "fresca", "serena", "viva", "pura", "azul", "tranquila"]),
                               str(r.randint(1000, 9999))])}
        _save("device.json", d)
    return d["name"]

settings = {"interval_min": 360, "auto": False, **_load("settings.json", {})}

def save_settings():
    _save("settings.json", settings)
