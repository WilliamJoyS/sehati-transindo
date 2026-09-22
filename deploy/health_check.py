"""Exit nonzero for failed service, HTTPS endpoint, or low disk space."""
import json
import shutil
import subprocess
import urllib.request
from manage import ROOT, compose


def main():
    config = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines()
                  if line and not line.startswith("#"))
    for service in ("app", "db", "caddy"):
        container = compose("ps", "-q", service, capture_output=True, text=True).stdout.strip()
        if not container:
            raise SystemExit(f"{service} is not running.")
        state = json.loads(subprocess.run(["docker", "inspect", "--format", "{{json .State}}", container],
                                         check=True, capture_output=True, text=True).stdout)
        if not state.get("Running") or (service in {"app", "db"} and state.get("Health", {}).get("Status") != "healthy"):
            raise SystemExit(f"{service} is not healthy.")
    with urllib.request.urlopen(f"https://{config['DOMAIN']}/api/health", timeout=15) as response:
        if json.load(response).get("status") != "ok":
            raise SystemExit("HTTPS health endpoint did not return ok.")
    disk = shutil.disk_usage(ROOT)
    if disk.used / disk.total > 0.85:
        raise SystemExit("Disk usage exceeds 85%; review storage and backups.")
    print("Services, HTTPS, database and disk checks passed.")


if __name__ == "__main__":
    main()
