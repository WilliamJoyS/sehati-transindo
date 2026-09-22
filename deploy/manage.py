"""VPS migration and backup helper; refuses to restore into a populated database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def compose(*args, **kwargs):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, **kwargs)


def sql(statement, database="sehati"):
    result = compose("exec", "-T", "db", "psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-U", "sehati_admin", "-d", database, "-At", input=statement, text=True, capture_output=True)
    return result.stdout.strip()


def restore_dump(path, database="sehati"):
    with path.open("rb") as stream:
        compose("exec", "-T", "db", "pg_restore", "-U", "sehati_admin", "--role=sehati_app",
            "--no-owner", "--no-acl", "--single-transaction", "--exit-on-error", "-d", database, stdin=stream)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def restore(path):
    path = path.resolve(strict=True)
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Expected a PostgreSQL custom-format dump.")
    manifest = path.with_suffix(".json")
    if not manifest.exists() or json.loads(manifest.read_text(encoding="utf-8"))["sha256"] != sha256(path):
        raise ValueError("Missing/mismatched backup checksum manifest.")
    running = compose("ps", "--status", "running", "--services", capture_output=True, text=True).stdout.split()
    if set(running) & {"app", "caddy"}:
        raise ValueError("Stop app and caddy before restoring. This helper never stops them automatically.")
    if sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';") != "0":
        raise ValueError("Target database is not empty. Nothing overwritten. Restore into a fresh VPS/volume.")
    restore_dump(path)
    sanitize_restored_access()
    print("Restored delivery rows:", sql("SELECT count(*) FROM deliveries;"))
    print("Old sessions, recovery codes and API keys are disabled in this VPS copy. Activate admin_sehati next.")


def sanitize_restored_access():
    # Only copied credentials/sessions are disabled. All business rows and audit history remain.
    sql("""BEGIN;
        TRUNCATE staff_sessions,mfa_enrollments,mfa_activation_grants,mfa_initial_permissions,
            mfa_recovery_codes,login_attempts,partner_rate_limits;
        UPDATE staff_accounts SET active=false;
        UPDATE api_clients SET active=false,revoked_at=COALESCE(revoked_at,now());
        INSERT INTO audit_events(action) VALUES('vps_restore_awaiting_admin_activation');
        COMMIT;""")


def verify_restore(path):
    database = "sehati_restore_" + uuid4().hex
    if not re.fullmatch(r"sehati_restore_[a-f0-9]{32}", database):
        raise ValueError("Unexpected verification database name.")
    sql(f"CREATE DATABASE {database} OWNER sehati_app;", "postgres")
    try:
        restore_dump(path, database)
        return int(sql("SELECT count(*) FROM deliveries;", database))
    finally:
        # The only automatic deletion is this exact, newly-created disposable verification DB.
        sql(f"DROP DATABASE {database} WITH (FORCE);", "postgres")


def backup():
    os.umask(0o077)
    folder = ROOT / "backups" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True, mode=0o700)
    path = folder / "database.dump"
    with path.open("xb") as stream:
        compose("exec", "-T", "db", "pg_dump", "-U", "sehati_admin", "--format=custom",
            "--no-owner", "--no-acl", "-d", "sehati", stdout=stream)
    count = verify_restore(path)
    shutil.copyfile(ROOT / "secrets" / "authenticator_key", folder / "authenticator.key")
    (folder / "authenticator.key").chmod(0o600)
    manifest = {"sha256": sha256(path), "restore_verified": True, "restored_deliveries": count,
                "created_at": datetime.now(timezone.utc).isoformat()}
    path.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Verified local backup: {folder.name}; {count} delivery rows.")
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--file", type=Path, default=ROOT / "migration" / "database.dump")
    sub.add_parser("backup")
    verify_parser = sub.add_parser("verify-restore")
    verify_parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "restore":
        restore(args.file)
    elif args.command == "backup":
        backup()
    else:
        print("Verified restored rows:", verify_restore(args.file))


if __name__ == "__main__":
    main()
