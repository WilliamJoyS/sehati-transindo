-- Explicit, expiring operator permission for first phone pairing only.
-- No existing account is automatically eligible, including legacy local accounts.
CREATE TABLE mfa_initial_permissions (
    staff_id uuid PRIMARY KEY REFERENCES staff_accounts(id) ON DELETE CASCADE,
    account_binding text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE mfa_enrollments ADD COLUMN initial_setup boolean NOT NULL DEFAULT false;
