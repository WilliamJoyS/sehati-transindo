"""Verified local dump, then encrypted remote backup. No silent local-only success."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from manage import ROOT, backup


def main():
    config = ROOT / "secrets" / "backup.env"
    if not config.exists():
        raise SystemExit("Off-server backup not configured: create secrets/backup.env first.")
    env = os.environ.copy()
    allowed = {"RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE", "AWS_ACCESS_KEY_ID",
               "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"}
    for line in config.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key not in allowed or not value.strip():
            raise SystemExit("Invalid backup setting. Use deploy/backup.env.example; no shell expressions.")
        env[key] = value.strip()
    repository = env.get("RESTIC_REPOSITORY", "")
    if not repository.startswith(("sftp:", "s3:", "rest:")) or "localhost" in repository or "127.0.0.1" in repository:
        raise SystemExit("Set a remote restic repository before enabling this job.")
    if not Path(env.get("RESTIC_PASSWORD_FILE", "/nonexistent")).is_file() or not shutil.which("restic"):
        raise SystemExit("Restic or its private repository password file is missing.")
    # Fail before creating another local backup if remote credentials/repository fail.
    subprocess.run(["restic", "snapshots", "--compact"], env=env, check=True)
    folder = backup()
    subprocess.run(["restic", "backup", str(folder), "--tag", "sehati", "--host", "sehati-vps"], env=env, check=True)
    subprocess.run(["restic", "check"], env=env, check=True)
    print("Off-server backup completed, encrypted, and repository checked.")


if __name__ == "__main__":
    main()
