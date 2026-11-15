import ftplib, io
import config

ENV = config.DATA / "infinityfree.env"
PHP = (config.ROOT / "deploy/redirect/index.php").read_bytes()
last_url = last_error = None

def creds():
    try:
        return dict(l.strip().split("=", 1) for l in ENV.read_text().splitlines() if "=" in l and not l.startswith("#"))
    except FileNotFoundError:
        return None

def publish(url):
    """Upload the redirector + current tunnel URL; try FTPS first, plain FTP as fallback."""
    global last_url, last_error
    c, err = creds(), None
    for cls in (ftplib.FTP_TLS, ftplib.FTP):
        try:
            with cls(c["FTP_HOST"], timeout=30) as f:
                f.login(c["FTP_USER"], c["FTP_PASS"])
                if cls is ftplib.FTP_TLS:
                    f.prot_p()
                f.cwd(c.get("FTP_DIR", "htdocs"))
                f.storbinary("STOR index.php", io.BytesIO(PHP))
                f.storbinary("STOR url.txt", io.BytesIO(url.encode()))
            last_url, last_error = url, None
            return
        except Exception as e:
            err = e
    last_error = str(err)[:200]
    raise err
