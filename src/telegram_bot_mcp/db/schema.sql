-- Launch-gate schema. Idempotent: safe to run on every startup.
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

-- One row per approval request the routine sends. The nonce is echoed in the
-- inline-button callback data; the webhook matches a tap against a still-pending
-- row before minting, which defeats replayed or stale taps.
--
-- roe_hash / company_name / scope_hosts are SNAPSHOTTED from the signed
-- engagement at request time. The operator approves what these columns describe,
-- and the mint binds to this snapshot's roe_hash — so a later re-signing of the
-- engagement cannot change what an already-shown request authorizes.
CREATE TABLE IF NOT EXISTS pending_approval (
    engagement_id TEXT NOT NULL,
    nonce         TEXT NOT NULL,
    roe_hash      TEXT NOT NULL,
    company_name  TEXT NOT NULL DEFAULT '',
    scope_hosts   TEXT[] NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'cancelled')),
    chat_id       BIGINT,
    message_id    BIGINT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ,
    PRIMARY KEY (engagement_id, nonce)
);

-- One-time, time-limited launch token bound to engagement + signed RoE hash.
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
