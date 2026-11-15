# ALCI · Agua Limpia, Ciudad Inteligente

Monitor de calidad de agua para tinacos y cisternas. Una Raspberry Pi toma una muestra, mide turbidez, pH y temperatura, calcula una calificación de 0 a 100 y un modelo de lenguaje local explica qué le pasa al agua y qué hacer, buscando información en la web. Se consulta desde cualquier lugar con una URL pública gratuita.

## Hardware

| Pieza | Para qué | Conexión |
|---|---|---|
| Raspberry Pi 5 (8 GB) | Cerebro, servidor y modelo local | |
| ADS1115 | Convertidor analógico | I2C 0x48 (SDA/SCL) |
| SEN0189 | Turbidez | A0, con divisor 10k/10k |
| PH-4502C | pH | A1, con divisor 10k/10k |
| DS18B20 | Temperatura | 1-Wire, GPIO4 |
| Arduino Uno | Controla las bombas | USB a la Pi, pines 7 y 8 |
| Módulo de relevadores (activo en bajo) | Enciende cada bomba | IN1 al pin 7, IN2 al pin 8 |
| 2 bombas R385 | Llenar y vaciar el contenedor de muestra | 12 V aparte, por COM y NO de cada relevador |

Los sensores de 5 V pasan por un divisor de voltaje de 10k/10k para no pasar de 3.3 V al ADS1115. Las bombas se alimentan con su propio adaptador de 12 V y un diodo 1N4007 en cada una, con la raya hacia el positivo. El negativo del adaptador no se une a la Pi ni al Arduino.

## Cómo funciona un ciclo

1. La bomba de entrada llena el contenedor desde el tinaco.
2. Se esperan unos segundos a que el agua se asiente y se miden turbidez, pH y temperatura.
3. La bomba de salida devuelve la muestra al tinaco.
4. Se calcula la calificación y el modelo local analiza el resultado y los últimos 30 días.

Calificación: pH 40 %, turbidez 45 %, temperatura 15 %. Si alguna parte baja de 20, el total no pasa de 40.

## Software

- Python 3.13, FastAPI y Uvicorn (`server/app.py`), SQLite (`server/store.py`).
- Ollama en el propio equipo con `qwen3.5:4b`, con búsqueda web y lectura de páginas. Si el modelo falla, un análisis basado en reglas lo reemplaza (`server/analysis.py`).
- Lectura de sensores con `smbus2` y `gpiozero`; las bombas, por USB serial al Arduino (`server/sensors.py`, `deploy/arduino_pumps/`).
- Interfaz web en HTML, CSS y JavaScript sin dependencias, con versión de escritorio (`static/desktop.html`) y de celular (`static/mobile.html`). El tinaco se representa con una gota que se llena según la calificación.
- Acceso desde Internet con un túnel de Cloudflare y un nombre aleatorio por equipo. Opcionalmente, un redirector en InfinityFree (`server/redirect.py`, `deploy/redirect/`).
- Arranque automático con systemd y actualización mensual del sistema.

## Instalación

Pensado para una Raspberry Pi con Raspberry Pi OS, un usuario llamado `alci` y el proyecto en `/home/alci/Documents/alci` (esas rutas están fijas en `deploy/install.sh` y `deploy/tunnel.sh`). Con I2C y 1-Wire activados:

```
git clone https://github.com/carl0srmz/alci.git /home/alci/Documents/alci
cd /home/alci/Documents/alci
python3 -m venv --system-site-packages .venv
.venv/bin/pip install fastapi uvicorn numpy smbus2 gpiozero pyserial requests ddgs
```

Antes del instalador necesitas Ollama en `~/.local/ollama` con el modelo descargado (`ollama pull qwen3.5:4b`) y `cloudflared` en `~/.local/bin`. Después:

```
sudo bash deploy/install.sh
```

El instalador registra los servicios `ollama`, `alci` y `alci-tunnel`, un temporizador mensual de actualizaciones del sistema y los permisos para actualizar y reiniciar desde el panel. La contraseña de administrador se crea en `data/ADMIN_PASSWORD.txt` al primer arranque.

La lista de paquetes de Python la armé a mano a partir de lo que importa el código, y no la he probado en una instalación limpia.

### Bombas con Arduino

Sube `deploy/arduino_pumps/arduino_pumps.ino` a un Arduino Uno y conéctalo por USB. El servidor encuentra el puerto solo. Para activarlas, agrega estas líneas en un `override.conf` del servicio `alci`:

```
[Service]
Environment=ALCI_PUMPS=1
Environment=ALCI_PUMP_ACTIVE_LOW=1
```

Mide cuánto tarda tu contenedor en llenarse y vaciarse, y ajusta `ALCI_FILL_S`, `ALCI_SETTLE_S` y `ALCI_DRAIN_S`.

## Calibración

Desde la pestaña Dispositivo de la interfaz de administrador:

- **pH:** asistente con soluciones buffer de 4.00, 6.86 y 9.18. Se ajusta una recta `pH = m·V + b`.
- **Turbidez:** se mide con agua limpia como referencia. El resultado es relativo, no un valor absoluto en NTU.

## Variables de entorno

| Variable | Por defecto | Qué hace |
|---|---|---|
| `ALCI_PORT` | 8080 | Puerto del servidor |
| `ALCI_MODEL` | qwen3.5:4b | Modelo de Ollama |
| `ALCI_PH_CH`, `ALCI_TURB_CH` | 1, 0 | Canales del ADS1115 |
| `ALCI_PH_SCALE`, `ALCI_TURB_SCALE` | 2.0 | Factor del divisor de voltaje |
| `ALCI_PUMPS` | 0 | Activa las bombas |
| `ALCI_PUMP_ACTIVE_LOW` | 1 | El módulo de relevadores se activa con nivel bajo |
| `ALCI_PUMP_SERIAL` | (automático) | Puerto del Arduino, si no quieres la búsqueda automática |
| `ALCI_FILL_S`, `ALCI_SETTLE_S`, `ALCI_DRAIN_S` | 40, 20, 45 | Tiempos del ciclo en segundos |

## Seguridad

El panel es de solo lectura para cualquier visitante. Las acciones de administración (calibrar, medir, actualizar, reiniciar) piden la contraseña. La carpeta `data/` guarda la base de datos, las calibraciones y las credenciales, y no se sube al repositorio. Para el redirector copia `data/infinityfree.env.example` a `data/infinityfree.env` y complétalo.

## Estructura

```
server/   API, sensores, análisis, base de datos, redirector
static/   interfaz de escritorio y de celular, fuentes
deploy/   instalador, túnel, programa del Arduino, redirector PHP
data/     datos locales, no versionados
```
