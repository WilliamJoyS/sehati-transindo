-- Local inspection schema only. No delivery/trip/charge tables are created until
-- their identities and grouping rules are approved. No spreadsheet rows are upserted.
CREATE TABLE IF NOT EXISTS staff_accounts (
    id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    totp_encrypted text NOT NULL,
    role text NOT NULL CHECK (role IN ('admin', 'importer', 'viewer')),
    active boolean NOT NULL DEFAULT true,
    last_totp_step bigint NOT NULL DEFAULT -1,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS staff_sessions (
    token_hash text PRIMARY KEY,
    staff_id uuid NOT NULL REFERENCES staff_accounts(id),
    csrf_token text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS session_staff_idx ON staff_sessions(staff_id);
CREATE TABLE IF NOT EXISTS preview_batches (
    id uuid PRIMARY KEY,
    staff_id uuid REFERENCES staff_accounts(id),
    filename text NOT NULL,
    file_digest text NOT NULL,
    mapping_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('preview_only', 'rejected')),
    report jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS batch_digest_idx ON preview_batches(file_digest, mapping_version);
CREATE TABLE IF NOT EXISTS audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id uuid REFERENCES staff_accounts(id),
    action text NOT NULL,
    object_id text,
    details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL,
    successful boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attempts_date_idx ON login_attempts(created_at);
