#!/bin/bash
# Run once:  sudo bash deploy/install.sh
set -e
[ "$EUID" = 0 ] || { echo "usa sudo"; exit 1; }
U=alci; R=/home/alci/Documents/alci; L=/home/alci/.local

cat > /usr/local/sbin/alci-update <<'X'
#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get -y -o Dpkg::Options::=--force-confold full-upgrade && apt-get -y autoremove
X
chmod 755 /usr/local/sbin/alci-update
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/alci-update, /usr/sbin/reboot\n' $U > /etc/sudoers.d/alci
chmod 440 /etc/sudoers.d/alci; visudo -cf /etc/sudoers.d/alci

unit() { # name, description, after, extra [Service] lines
cat > /etc/systemd/system/$1.service <<X
[Unit]
Description=$2
After=$3
[Service]
User=$U
Restart=always
RestartSec=5
$4
[Install]
WantedBy=multi-user.target
X
}
unit ollama "ALCI local LLM" network-online.target "Environment=OLLAMA_MODELS=$L/ollama/models OLLAMA_KEEP_ALIVE=30m OLLAMA_HOST=127.0.0.1
ExecStart=$L/ollama/bin/ollama serve"
unit alci "ALCI server" "ollama.service" "WorkingDirectory=$R
ExecStart=$R/.venv/bin/python server/app.py"
unit alci-tunnel "ALCI public tunnel" "network-online.target alci.service" "ExecStart=/bin/bash $R/deploy/tunnel.sh"

cat > /etc/systemd/system/alci-update.service <<X
[Unit]
Description=ALCI monthly Linux update
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/alci-update
X
cat > /etc/systemd/system/alci-update.timer <<X
[Unit]
Description=ALCI monthly Linux update
[Timer]
OnCalendar=monthly
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
X
systemctl daemon-reload
systemctl enable --now ollama alci alci-tunnel alci-update.timer
echo "Listo. Contraseña admin: $(cat $R/data/ADMIN_PASSWORD.txt 2>/dev/null || echo '(se crea al primer arranque)')"
