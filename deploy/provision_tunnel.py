"""One-time: give this device a stable <device-name>.<ALCI_DOMAIN> via Cloudflare named tunnel.
Needs CF_API_TOKEN (Tunnel:Edit + DNS:Edit), CF_ACCOUNT_ID, CF_ZONE_ID, ALCI_DOMAIN in the env."""
import json, os, secrets, sys
import requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
import config

e = os.environ
api = "https://api.cloudflare.com/client/v4"
H = {"Authorization": f"Bearer {e['CF_API_TOKEN']}"}
host = f"{config.device_name()}.{e['ALCI_DOMAIN']}"

def call(method, path, **kw):
    r = requests.request(method, api + path, headers=H, timeout=30, **kw).json()
    if not r["success"]:
        sys.exit(f"{path}: {r['errors']}")
    return r["result"]

t = call("POST", f"/accounts/{e['CF_ACCOUNT_ID']}/cfd_tunnel",
         json={"name": f"alci-{config.device_name()}", "tunnel_secret": secrets.token_urlsafe(32), "config_src": "cloudflare"})
call("PUT", f"/accounts/{e['CF_ACCOUNT_ID']}/cfd_tunnel/{t['id']}/configurations",
     json={"config": {"ingress": [{"hostname": host, "service": f"http://127.0.0.1:{config.PORT}"}, {"service": "http_status:404"}]}})
call("POST", f"/zones/{e['CF_ZONE_ID']}/dns_records",
     json={"type": "CNAME", "name": host, "content": f"{t['id']}.cfargotunnel.com", "proxied": True})
config._save("tunnel.json", {"hostname": host, "token": t["token"]})
print("Listo:", f"https://{host}", "- reinicia: sudo systemctl restart alci-tunnel")
