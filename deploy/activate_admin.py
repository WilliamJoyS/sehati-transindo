"""Activate the existing admin on the VPS, with a new password; no new account."""
import argparse
import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sehati-backend"))
from app import auth
from app.authenticator import allow_initial_setup, replace_recovery_codes
from app.db import connect, initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin_sehati")
    args = parser.parse_args()
    if not auth.PRODUCTION:
        raise SystemExit("This command must run inside the production app container.")
    initialize()
    password = getpass.getpass("Password BARU admin VPS (minimal 14 karakter): ")
    repeated = getpass.getpass("Ulangi password: ")
    if password != repeated or not 14 <= len(password) <= 256:
        raise SystemExit("Password tidak cocok atau panjangnya belum sesuai. Tidak ada perubahan.")
    codes = []
    with connect() as conn:
        auth.lock_auth(conn)
        account = conn.execute("SELECT * FROM staff_accounts WHERE username=%s FOR UPDATE", (args.username,)).fetchone()
        if not account or account["role"] != "admin":
            raise SystemExit("Existing administrator not found. Restore the supplied database first.")
        if auth.PASSWORDS.verify(password, account["password_hash"]):
            raise SystemExit("Gunakan password baru untuk VPS, berbeda dari password lokal.")
        # Wrong encryption keys must fail before any account is modified.
        auth.cipher().decrypt(account["totp_encrypted"].encode())
        conn.execute("UPDATE staff_accounts SET password_hash=%s,active=true,deletable=false WHERE id=%s",
                     (auth.PASSWORDS.hash(password), account["id"]))
        conn.execute("DELETE FROM staff_sessions WHERE staff_id=%s", (account["id"],))
        conn.execute("DELETE FROM mfa_enrollments WHERE staff_id=%s", (account["id"],))
        conn.execute("DELETE FROM mfa_activation_grants WHERE staff_id=%s", (account["id"],))
        conn.execute("DELETE FROM mfa_initial_permissions WHERE staff_id=%s", (account["id"],))
        if account["authenticator_enrolled_at"]:
            codes = replace_recovery_codes(conn, account["id"])
        conn.execute("INSERT INTO audit_events(actor_id,action) VALUES(%s,'production_admin_activated')", (account["id"],))
    if codes:
        print("Authenticator HP yang sudah terpasang tetap berlaku. Simpan kode pemulihan BARU ini secara pribadi:")
        print("\n".join(codes))
    else:
        allow_initial_setup(args.username)
        print("Pemasangan pertama Google Authenticator diizinkan selama 24 jam. Masuk di website untuk memindai QR.")
    print(f"Akun {args.username} siap. Tidak ada akun baru yang dibuat.")


if __name__ == "__main__":
    main()
