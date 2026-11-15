#!/bin/bash
# Named tunnel (stable <device>.<domain>) if provisioned, otherwise a free random trycloudflare.com URL.
D=/home/alci/Documents/alci/data
CF=/home/alci/.local/bin/cloudflared
if [ -f $D/tunnel.json ]; then
  exec $CF tunnel --no-autoupdate run --token "$(python3 -c "import json;print(json.load(open('$D/tunnel.json'))['token'])")"
fi
: > $D/tunnel.log
exec $CF tunnel --no-autoupdate --url http://127.0.0.1:8080 --logfile $D/tunnel.log
