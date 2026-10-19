-- 027: shared, tenant-scoped gateway request buckets.
--
-- Each tenant has one row because /v1, /v2 and ask.stream share the same allowance. The
-- gateway locks this row inside a short READ COMMITTED transaction before it refills and
-- consumes capacity. A new process or replica therefore observes the same bucket state.
--
-- This is request-rate state, not model token/currency accounting. No query, actor, client
-- IP, credential, document, or provider response is retained here. Tenants cascade so the
-- operational row has the same lifecycle as its owning tenant.

BEGIN;

CREATE TABLE IF NOT EXISTS gateway_rate_limits (
    tenant_id  uuid        PRIMARY KEY REFERENCES tenants (tenant_id) ON DELETE CASCADE,
    tokens     numeric     NOT NULL CHECK (tokens >= 0 AND tokens <= 10000),
    updated_at timestamptz NOT NULL
);

ALTER TABLE gateway_rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_rate_limits FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON gateway_rate_limits;
CREATE POLICY tenant_isolation ON gateway_rate_limits
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE gateway_rate_limits IS
    'Shared request token buckets; request-rate only, not model spend or user content.';

COMMIT;
