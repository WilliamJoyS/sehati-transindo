-- Existing authenticators remain valid until a verified replacement is confirmed.
ALTER TABLE staff_accounts ADD COLUMN authenticator_enrolled_at timestamptz;
CREATE TABLE mfa_activation_grants (
    staff_id uuid PRIMARY KEY REFERENCES staff_accounts(id) ON DELETE CASCADE,
    code_hash text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mfa_enrollments (
    token_hash text PRIMARY KEY,
    staff_id uuid NOT NULL UNIQUE REFERENCES staff_accounts(id) ON DELETE CASCADE,
    secret_encrypted text NOT NULL,
    account_binding text NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mfa_recovery_codes (
    staff_id uuid NOT NULL REFERENCES staff_accounts(id) ON DELETE CASCADE,
    code_hash text NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (staff_id, code_hash)
);
