# Sehati — local operational backend

> VPS COPY: Deployment instructions for this package are in ../PANDUAN-VPS.md.
> This file records the original local workflow; Windows start/stop/provisioning scripts
> and private local runtime files are not included in the deployable package.
> The copied application adds production configuration, Secure cookies, private database
> connectivity and authenticated API documentation. Do not follow local setup steps on the VPS.

The public website, staff portal, FastAPI and PostgreSQL run together locally. Staff can select a customer, upload Excel, review staged rows and validation notes, confirm an atomic import, inspect committed records and export an editable workbook. Administrators can issue/revoke customer-scoped API credentials and test the API locally.

This implements **Sehati's proposed v1 API**, not a connection to Bridgestone's external systems. No external partner request, blockchain deployment, public hosting or WhatsApp message is part of this release.

## Inspect and run

- Website: <http://127.0.0.1:8000/>
- Staff: <http://127.0.0.1:8000/admin/>
- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>
- Private PostgreSQL: `127.0.0.1:55432`, database `sehati_local`

Open `../sehati-local.code-workspace` in VS Code. New terminals start in the backend folder. Its tasks start/stop services or restart the backend and open Google Chrome. Alternatively, from this backend folder:

```powershell
.\scripts\start-local.ps1
.\scripts\start-local.ps1 -Restart -OpenChrome
.\scripts\stop-local.ps1
```

Start/stop preserves the database. `-Restart` reloads backend changes by restarting only this project's verified backend process tree, leaving PostgreSQL running. `-OpenChrome` opens the staff page in installed Google Chrome after the server is ready. Without `-Restart`, an already running backend is reused. Backend/database processes run hidden; unrelated processes on port 8000 are not stopped. The older website-only preview on port 4173 is optional; port 8000 serves the integrated site and backend.

Open `.local/LOGIN.md` privately for the inspection account. Obtain a single-use local test code with:

```powershell
.\.venv\Scripts\python.exe .\scripts\local_otp.py
```

Wait for the next code before signing in again. This helper is only for unpaired local inspection accounts and stops working once that account pairs its phone. `setup_local.py` provisions without rotating existing credentials; optional `--sample` stages but never confirms a workbook.

## Google Authenticator — no email required

Staff can pair a phone through **Pertama kali? Pasang Google Authenticator** on the login page. Enter the existing username/password, scan the QR on the phone and confirm the six-digit code. No long activation code or terminal command is required for staff. The account label uses the Sehati username; an email address or Google account is not required. QR generation is local using `qrcode`; no QR service receives the secret.

An operator must verify the account owner and explicitly allow first pairing for that named, unpaired account (24-hour expiry):

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_authenticator.py --username admin_sehati
```

The script writes instructions to `.local/AUTHENTICATOR-SETUP.md`; it does not print credentials, change the password, disable the existing factor, or create a staff account. Unpaired accounts are not automatically eligible. The permission is bound to the existing password hash and authenticator secret and is checked both at start and confirmation. Cancelled or expired QR setup can be restarted while permission remains valid; only the most recent QR can be confirmed. Successful pairing removes the permission. An already paired account cannot be enabled for first setup again.

During this explicitly authorized window, possession of that account's password is sufficient to begin first pairing. A stolen password could therefore allow someone else to enroll first; enable this only after verifying the owner, keep the window short, and use a strong privately delivered password. This is an onboarding permission, not a password-only MFA reset. Legacy code-based activation remains supported for operator integrations; issuing it removes the simpler permission, and vice versa.

For replacement phones, choose **Sudah pernah memasang? Ganti HP** or use **Akun saya**, then supply the existing authenticator code or an unused recovery code with the password. A pending QR expires after at most 15 minutes, allows at most five incorrect confirmations, and grants no staff session. Confirming the new code atomically replaces the encrypted secret, invalidates old sessions/pending permissions/recovery codes, and issues a new session plus ten recovery codes. The confirmation OTP cannot be replayed for another login. Existing authenticators remain valid until confirmation.

Recovery codes are shown once, downloadable as a private text file, and only SHA-256 hashes of random 128-bit codes are stored. **Gunakan kode pemulihan** signs in using the password plus one unused code and revokes previous sessions. **Akun saya → Buat ulang kode pemulihan** requires the current password, a fresh authenticator code, session, and CSRF; it replaces all previous recovery codes. Keep the downloaded file private and separate from the authenticator phone. Losing both the phone and all recovery codes requires a separately verified operator recovery process; there is deliberately no password-only or email reset endpoint.

Activation, confirmation failures, replacement, recovery-code use and regeneration are audited without storing plaintext secrets in audit details. Login and enrollment proofs share the local brute-force limit. All of these routes retain the application's loopback-only restriction; public VPS configuration and production account lifecycle remain separate deployment work.

## Import rules

The supplied `BRIDGESTONE 2025.xlsx` has nine billing-period sheets, 826 delivery rows, 819 distinct D/O values and one standalone charge. D/O is **not** a unique record key. Repeated D/O rows remain separate with internal UUIDs. Billing periods come from sheet contents, not Sheet1–Sheet9 names.

Blank grouped cells stay null. Amounts are kept as reported. No trips, charge allocation, tax calculation, GPS or proof of delivery is inferred. Standalone charges belong to their invoice. Summary/tax footers and auxiliary rate tables are excluded from deliveries. This is an operational import, not an accounting ledger replacement.

1. Select/create the customer. Every invoice, delivery, charge, import and partner credential belongs to a customer.
2. Upload `.xlsx`: maximum 10 MB and 10,000 business rows. Checks cover archive expansion, hidden sheets, headers, types, IDs, duplicates, supported formulas and ownership. Temporary uploads are deleted after processing.
3. Review new/updated/unchanged rows, field changes, periods and warnings. Blocking errors prevent the entire commit. Preview changes no business records.
4. Confirm. One PostgreSQL transaction locks the customer's import stream, rechecks versions, writes accepted records/audit and advances `data_version`. Conflicts/write failures roll back all business changes and mark the batch failed. Export current data, correct it and upload a fresh preview.
5. For corrections, retain exported record IDs, charge IDs and versions. Blank editable fields clear those fields after review; **missing rows never delete records**. Leave ID and version blank only for genuinely new rows. Stale versions and cross-customer IDs are blocked.

Identical or semantically identical committed uploads replay without writes, including re-saved copies and concurrent confirmations. Re-uploading the original legacy workbook cannot undo later corrections. Changed legacy invoices without stable IDs are blocked; use the editable export. D/O and Excel row position never silently choose a record to update.

Structured source rows, changes, reports and audits persist in PostgreSQL; original uploaded files are not archived. Keep the source workbook separately. Never put exports, backups, credentials or logs inside the public website or `admin/`.

## Database and implementation

| Tables | Purpose |
| --- | --- |
| `customers` | Ownership and committed data revision |
| `billing_documents` | Invoice reference and billing period |
| `deliveries` | Operational rows with stable IDs/versions |
| `invoice_lines` | Reported charges linked to a delivery or invoice |
| `import_batches`, `import_rows` | Preview/status, source, before/after changes |
| `legacy_document_snapshots` | Recognize previously imported legacy documents |
| `api_clients`, `partner_rate_limits` | Hashed keys, scope, expiry, throttling |
| `staff_accounts`, `staff_sessions`, `login_attempts` | Authentication |
| `mfa_initial_permissions`, `mfa_activation_grants`, `mfa_enrollments`, `mfa_recovery_codes` | Explicit first-pairing permission, optional activation grants, expiring pending QR setup, hashed single-use recovery codes |
| `audit_events`, `schema_migrations` | Audit and checksummed upgrades |
| `preview_batches` | Archive from the earlier preview-only release |

`app/import_engine.py` maps workbooks; `app/operations.py` imports/exports; `app/partner.py` handles partner access; `app/main.py` exposes staff routes; `app/auth.py` enforces authentication. `schema.sql` and `migrations/` upgrade transactionally. Never edit an applied migration; add a new one.

The schema supports multiple customers. The legacy parser is specific to the supplied layout. Other customers can use the stable-ID template or get a reviewed adapter for their workbook. Invoice references/periods remain stable; document-metadata corrections need a future explicit workflow. No fabricated trip, fleet-management or blockchain tables exist.

## Partner contract

Create credentials under **API Partner**. The full key is returned once, kept in browser memory only and stored as a hash in PostgreSQL. Credentials expire and can be revoked. Scope is `deliveries:read`; fields are allowlisted. Financial amounts and internal notes are excluded.

Send `X-API-Key` as a header:

| Endpoint | Result |
| --- | --- |
| `GET /api/partner/v1/status` | Contract, customer scope, allowed fields |
| `GET /api/partner/v1/deliveries` | Paginated committed deliveries |
| `GET /api/partner/v1/deliveries/{id}` | One record within credential scope |

Lists return `data` and `meta` (`total`, `limit`, `offset`, `next_offset`, `data_version`). Start at offset 0, then carry `data_version` into subsequent pages. On 409 discard partial results and restart. Maximum page size: 100. Limit: 120 authenticated requests/minute/client; 429 provides `Retry-After`. Keys must not be in URLs or frontend source. Dates are ISO; decimals are strings to preserve precision. Customer scope comes from the credential. Responses read committed PostgreSQL data, never Excel directly.

Save a newly issued test key privately to `.local/partner-test.key`, then test all pages through real HTTP:

```powershell
.\.venv\Scripts\python.exe .\scripts\partner_client.py --key-file .local/partner-test.key
```

The client permits loopback HTTP only, disables proxies/redirects and prints counts rather than credentials/records. Revoke test credentials after use. Before external integration, agree fields, direction, authentication, update frequency, format and availability with the partner, then implement their adapter.

## Security and recovery

Passwords use Argon2; PyOTP verifies single-use codes; authenticator secrets are encrypted. PostgreSQL sessions expire after 30 minutes idle/eight hours absolute with HttpOnly/SameSite=Strict cookies. Writes require allowed Origin, CSRF and roles. Parameterized SQL, private upload paths, strict validation, size limits, safe rendering and persisted API throttling are enabled. Staff viewers can read all customers; partner access is restricted to one. Individual staff lifecycle/provisioning UI remains future work.

Only loopback peers/hosts are accepted. `.local/` is ignored by Git, restricted by current-user/SYSTEM ACL and outside web roots. It contains credentials, encryption key, logs and persistent `pgdata/`. Portable PostgreSQL is under `work/runtime/postgresql-18.6/pgsql`. No firewall opening, public listener, cloud resource or Windows service is created.

Create a private archive and restore it into an isolated disposable database:

```powershell
.\.venv\Scripts\python.exe .\scripts\backup_local.py --verify-restore
```

Archives/manifests stay in `.local/backups/`. Restoration is checked and the restored delivery count recorded. Preserve the application encryption key separately and securely: a dump alone cannot decrypt TOTP secrets. After restoring an older backup, revoke restored sessions and activation/pending grants and replace recovery codes before reopening access; a backup may contain codes that were consumed after it was created. Local backups do not protect against disk loss. Before hosting, add automated encrypted off-server backups, retention, restoration drills, monitoring/alerts, updates, HTTPS/Secure cookies, staff provisioning/verified operator recovery and deployment security review. This is a local operational release, not a production-readiness or unhackability claim.

## Tests and dependencies

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Tests use disposable `sehati_test_*` databases, never replace `sehati_local`, and cover sample preservation, stable updates, missing-row retention, replay/races, stale data, rollback, customer isolation, field scopes, credential lifecycle, throttling, snapshots, login, upload validation and the local client. Private workbook cases skip without the sample.

`requirements.lock.txt` pins dependencies. Recreating the environment also needs supported Python and separately provisioned PostgreSQL/secrets:

```powershell
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.lock.txt
```
