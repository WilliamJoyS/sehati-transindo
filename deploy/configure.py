"""Run on the VPS once, before starting PostgreSQL. Standard library only."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets

ROOT = Path(__file__).resolve().parents[1]


def configure(root, domain, email, key_file):
    domain = domain.strip().lower()
    email = email.strip()
    if (len(domain) > 253 or "." not in domain or domain == "localhost"
            or re.fullmatch(r"[0-9.]+", domain)
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in domain.split("."))):
        raise ValueError("Use a real domain without https://, a port, or a path.")
    if not re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email):
        raise ValueError("Enter a valid administrator email for HTTPS certificate notices.")
    raw = key_file.read_text(encoding="utf-8").strip()
    if raw.startswith("{"):
        raw = json.loads(raw)["encryption_key"]
    if len(raw) != 44 or len(base64.b64decode(raw, altchars=b"-_", validate=True)) != 32:
        raise ValueError("The migrated authenticator encryption key is invalid.")
    folder = root / "secrets"
    if folder.exists() or (root / ".env").exists():
        raise ValueError("Configuration already exists; refused to overwrite database passwords or keys.")
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    for name, value in {"postgres_password": secrets.token_hex(32), "app_db_password": secrets.token_hex(32), "authenticator_key": raw}.items():
        path = folder / name
        path.write_text(value + "\n", encoding="utf-8")
        # Parent directory is owner-only. Each file is individually bind-mounted
        # read-only into its authorized containers (including the non-root app).
        path.chmod(0o444)
    env = root / ".env"
    env.write_text(f"DOMAIN={domain}\nACME_EMAIL={email}\n", encoding="utf-8")
    env.chmod(0o600)
    return domain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--key-file", type=Path, default=ROOT / "migration" / "app-secrets.json")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        domain = configure(ROOT, args.domain, args.email, args.key_file)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from error
    print(f"Configured https://{domain}. Secret values were not printed. Next: start db and restore the dump.")


if __name__ == "__main__":
    main()
