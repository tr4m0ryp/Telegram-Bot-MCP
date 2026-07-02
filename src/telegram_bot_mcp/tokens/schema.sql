-- Launch-token store. Idempotent: safe to run on every startup.
--
-- `engagement` is the integration seam to the enrichment engagement store: in
-- production it is the table (or a view over it) that signature-verification
-- populates with each engagement's signed Rules-of-Engagement hash and scope.
-- Point DATABASE_URL at the enrichment Postgres and this becomes a no-op if the
-- table already exists there with these columns.

CREATE TABLE IF NOT EXISTS engagement (
    engagement_id TEXT PRIMARY KEY,
    company_name  TEXT NOT NULL,
    scope_hosts   TEXT[] NOT NULL DEFAULT '{}',
    roe_hash      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS launch_token (
    token         TEXT PRIMARY KEY,
    engagement_id TEXT NOT NULL,
    roe_hash      TEXT NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    used_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS launch_token_engagement_idx
    ON launch_token (engagement_id);
