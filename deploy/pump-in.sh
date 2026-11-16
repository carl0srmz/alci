#!/bin/bash
# Runs the in pump until Ctrl+C (or max seconds, default 180) and prints how long it ran.
cd "$(dirname "$0")/../server" || exit 1
echo "Bomba in encendida. Ctrl+C para detenerla."
../.venv/bin/python -c "
import sensors, config, time
t = time.time()
try: sensors._run_pump(config.PUMP_IN_PIN, int(${1:-180}))
except KeyboardInterrupt: pass
print('tiempo:', round(time.time() - t - 2), 's')"
