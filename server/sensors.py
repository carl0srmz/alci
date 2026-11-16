import fcntl, glob, os, statistics, threading, time
import numpy as np
from smbus2 import SMBus
import config

ADS_ADDR = 0x48
_lock = threading.Lock()  # one I2C user at a time

def _volts(bus, ch):
    cfg = 0x8000 | ((4 + ch) << 12) | (0b001 << 9) | 0x0100 | (0b111 << 5) | 0b11  # single-shot, ±4.096 V, 860 SPS (A1 vs GND = 0xD3E3)
    bus.write_i2c_block_data(ADS_ADDR, 0x01, [cfg >> 8, cfg & 0xFF])
    time.sleep(0.002)
    hi, lo = bus.read_i2c_block_data(ADS_ADDR, 0x00, 2)
    raw = (hi << 8) | lo
    return (raw - 65536 if raw & 0x8000 else raw) * 0.000125

def read_volts(ch, n=50, gap=0.0):
    with _lock, SMBus(1) as bus:
        vals = []
        for _ in range(n):
            vals.append(_volts(bus, ch))
            time.sleep(gap)
    return statistics.median(vals), (statistics.pstdev(vals) if n > 1 else 0.0)

def temperature():
    for p in glob.glob("/sys/bus/w1/devices/28-*/temperature"):
        try:
            return int(open(p).read()) / 1000
        except Exception:
            pass
    return None

# ---- pH ----
def _cal():
    return config._load("calibration.json", None)

def ph_from_v(v):
    c = _cal()
    if c:
        return c["m"] * v + c["b"], True
    return 7 + (2.5 - v) / 0.18, False  # nominal PH-4502C curve, rough until calibrated

def capture_buffer(ph_value):
    """~10 s in a buffer. Judge stability by drift of the mean (first vs second half), not by raw noise:
    the PH-4502C is always noisy (±20 mV) but a settled probe has a steady average."""
    vs = []
    for _ in range(40):
        vs.append(read_volts(config.PH_CH, n=5)[0] * config.PH_SCALE)
        time.sleep(0.25)
    drift = abs(statistics.mean(vs[20:]) - statistics.mean(vs[:20]))
    if drift > 0.02:
        raise ValueError(f"La sonda aún se está asentando (el voltaje se movió {drift*1000:.0f} mV en 10 s). Espera un poco más y repite.")
    return {"buffer": ph_value, "v": statistics.mean(vs)}

def fit_calibration(points):
    if len(points) < 2:
        raise ValueError("Se necesitan al menos 2 soluciones.")
    v = np.array([p["v"] for p in points])
    ph = np.array([p["buffer"] for p in points])
    if len(set(np.round(v, 3))) < len(v):
        raise ValueError("Dos soluciones dieron el mismo voltaje; revisa la sonda.")
    m, b = np.polyfit(v, ph, 1)
    err = float(np.max(np.abs(m * v + b - ph)))
    cal = {"m": float(m), "b": float(b), "max_err": err, "points": points, "ts": int(time.time())}
    config._save("calibration.json", cal)
    return cal

# ---- turbidity (SEN0189, DFRobot curve) ----
def _turb_ref():
    c = config._load("calibration_turb.json", None)
    return c["v_clear"] if c else None

def capture_clear_water():
    """One-point calibration: the clear-water *floor* becomes the 4.2 V (0 NTU) point of the DFRobot curve.
    In clean water the SEN0189 sits pinned at a ceiling and flickers between a few levels, so anchoring at the
    lowest level (2nd percentile) keeps clear water at 0 NTU instead of jumping.
    shortcut: no formazin standards, so NTU is relative to clean water, not absolute; upgrade with a 2nd standard."""
    with _lock, SMBus(1) as bus:
        vs = sorted(_volts(bus, config.TURB_CH) * config.TURB_SCALE for _ in range(300))
    v, sd = vs[len(vs) // 50], statistics.pstdev(vs)
    if sd > 0.05:
        raise ValueError(f"Lectura inestable (±{sd*1000:.0f} mV). Espera a que no haya burbujas ni movimiento y repite.")
    if v < 2.5:
        raise ValueError(f"{v:.2f} V es muy bajo para agua limpia. Revisa que el sensor esté alimentado y limpio.")
    cal = {"v_clear": v, "ts": int(time.time())}
    config._save("calibration_turb.json", cal)
    return cal

def ntu_from_v(v):
    ref = _turb_ref()
    if ref:
        v = v * 4.2 / ref
    if v >= 4.2: return 0.0
    if v < 2.5: return 3000.0
    return max(0.0, -1120.4 * v * v + 5742.3 * v - 4352.9)

def measure():
    out, errors = {}, []
    try:
        v, sd = read_volts(config.PH_CH)
        out["ph_v"] = v * config.PH_SCALE
        out["ph_noise_mv"] = sd * config.PH_SCALE * 1000
        # a dry probe floats and is noisy: only complain when it should be submerged (pumps fill the tank)
        if config.PUMPS_ENABLED and out["ph_noise_mv"] > 20:
            errors.append(f"pH: lectura inestable (±{out['ph_noise_mv']:.0f} mV) con la muestra en el contenedor")
        out["ph"], out["ph_calibrated"] = ph_from_v(out["ph_v"])
        if not 0 <= out["ph"] <= 14:
            errors.append(f"pH: lectura imposible ({out['ph']:.1f}); revisa el cableado o calibra")
            del out["ph"]
    except Exception as e:
        errors.append(f"pH: {e}")
    try:
        v, _ = read_volts(config.TURB_CH)
        out["turb_v"] = v * config.TURB_SCALE
        out["turb_ntu"] = ntu_from_v(out["turb_v"])
    except Exception as e:
        errors.append(f"turbidez: {e}")
    out["temp_c"] = temperature()
    if out["temp_c"] is None:
        errors.append("temperatura: sensor no responde")
    out["errors"] = errors
    return out

# ---- pumps ----
_ARDUINO_VIDS = (0x2341, 0x2A03, 0x1A86, 0x0403)  # Arduino, Arduino.org, CH340 clones, FTDI

def _arduino_port():
    """ALCI_PUMP_SERIAL if it exists, else the first Arduino-like USB serial port (survives /dev/ttyUSBn renumbering)."""
    from serial.tools import list_ports
    if config.PUMP_SERIAL not in ("", "auto") and os.path.exists(config.PUMP_SERIAL):
        return config.PUMP_SERIAL
    found = [p.device for p in list_ports.comports() if p.vid in _ARDUINO_VIDS]
    return found[0] if found else None

def _open_arduino(tries=4):
    """Open the port and wait for the sketch to answer; re-discover and retry if it doesn't."""
    import serial
    last = "no se encontró el Arduino por USB"
    for _ in range(tries):
        port = _arduino_port()
        if port:
            try:
                s = serial.Serial(port, 9600, timeout=2)
                time.sleep(2)  # opening the port resets the Uno
                s.reset_input_buffer()
                s.write(b"P1 0\n")  # harmless: stops pump 1, the sketch answers "ok"
                if s.readline().strip() == b"ok":
                    return s
                s.close()
                last = f"{port}: el Arduino no responde (¿programa cargado?)"
            except (serial.SerialException, OSError) as e:
                last = f"{port}: {e}"
        time.sleep(1)
    raise RuntimeError("Bombas: " + last)

def _run_pump_serial(pin, seconds):
    n = 1 if pin == config.PUMP_IN_PIN else 2
    # one process at a time: opening the port resets the Uno, which cuts or glitches a pump another process is running
    with open(config.DATA / ".pumps.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with _open_arduino() as s:
            s.write(f"A {int(config.PUMP_ACTIVE_LOW)}\nP{n} {int(seconds)}\n".encode())
            try:
                time.sleep(seconds)
            finally:
                try:
                    s.write(f"P{n} 0\n".encode())
                except Exception:
                    pass  # the sketch stops the pump by itself when the time is up

def _run_pump(pin, seconds):
    if config.PUMP_SERIAL or _arduino_port():  # an Arduino on USB wins over GPIO even without the env var
        return _run_pump_serial(pin, seconds)
    from gpiozero import OutputDevice
    d = OutputDevice(pin, active_high=not config.PUMP_ACTIVE_LOW, initial_value=False)
    try:
        d.on(); time.sleep(seconds)
    finally:
        d.off(); d.close()

def fill_sample():
    if config.PUMPS_ENABLED:
        _run_pump(config.PUMP_IN_PIN, config.FILL_S)
        time.sleep(config.SETTLE_S)

def drain_sample():
    if config.PUMPS_ENABLED:
        _run_pump(config.PUMP_OUT_PIN, config.DRAIN_S)
