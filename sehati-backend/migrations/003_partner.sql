-- Sehati's proposed local v1 read API. No connection to an external partner.
CREATE TABLE IF NOT EXISTS api_clients (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    customer_id uuid NOT NULL REFERENCES customers(id),
    key_digest text NOT NULL UNIQUE,
    key_hint text NOT NULL,
    scopes text[] NOT NULL DEFAULT ARRAY['deliveries:read'],
    allowed_fields text[] NOT NULL,
    active boolean NOT NULL DEFAULT true,
    expires_at timestamptz NOT NULL,
    created_by uuid REFERENCES staff_accounts(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    last_used_at timestamptz
);
CREATE INDEX IF NOT EXISTS api_clients_customer_idx ON api_clients(customer_id);

-- One bounded row per credential; survives restarts and works across workers.
CREATE TABLE IF NOT EXISTS partner_rate_limits (
    client_id uuid PRIMARY KEY REFERENCES api_clients(id) ON DELETE CASCADE,
    window_start timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0)
);
