-- 035: the model-spend ledger, shared by every instance and surviving restarts.
--
-- Until now backend/budget.py kept spend in a local JSON file. On App Service that file is
-- lost on restart and is different on each instance, so every instance enforced the full
-- caps on its own. These two tables replace it whenever PLACEDON_DATABASE_URL is set.
--
-- model_spend: one counter row per (scope, period, day).
--   scope   'global', 'tenant:<firm id>', 'user:<person id>', 'model:<model name>' (request
--           count only), or 'flag:<name>' (a provider condition: the row existing is the flag).
--   period  'day' (day = that date) or 'month' (day = the first of the month).
--   spent_inr is rupees, the unit backend/budget.py uses, and INCLUDES live holds: a call
--   reserves its worst case with one conditional upsert per scope,
--       ... ON CONFLICT DO UPDATE SET spent_inr = spent_inr + x WHERE spent_inr + x <= cap
--   and settle gives back the unused part. No cap is stored here: caps live in code.
--
-- model_spend_holds: one row per reservation, so any instance can settle, claim or
-- inspect a hold another instance made, and a settlement retried is applied once.
--
-- ## Not tenant-scoped, on purpose (same decision as login_attempts in 026)
--
-- The global row is shared by every firm: a firm's call must add to it, and the gateway
-- must read every firm's spend to enforce the deployment cap. A tenant-bound policy would
-- make the global cap unenforceable. So both tables get FORCE ROW LEVEL SECURITY with an
-- explicit USING (true) policy: "no row restriction, on purpose", not a forgotten one.
-- They hold ids, model names and rupee amounts only: no document, prompt or answer text.

BEGIN;

CREATE TABLE IF NOT EXISTS model_spend (
    scope      text          NOT NULL CHECK (scope ~ '^(global|(tenant|user|model|flag):.+)$'),
    period     text          NOT NULL CHECK (period IN ('day', 'month')),
    day        date          NOT NULL,
    spent_inr  numeric(14,4) NOT NULL DEFAULT 0 CHECK (spent_inr >= 0),
    requests   integer       NOT NULL DEFAULT 0 CHECK (requests >= 0),
    -- The part of spent_inr settled at the hold because the provider reported no usage.
    held_inr   numeric(14,4) NOT NULL DEFAULT 0 CHECK (held_inr >= 0),
    PRIMARY KEY (scope, period, day),
    CHECK (period = 'day' OR date_trunc('month', day)::date = day)
);

CREATE TABLE IF NOT EXISTS model_spend_holds (
    reservation_id   text          PRIMARY KEY CHECK (length(reservation_id) BETWEEN 1 AND 200),
    day              date          NOT NULL,
    amount_inr       numeric(14,4) NOT NULL CHECK (amount_inr >= 0),
    requests         integer       NOT NULL CHECK (requests >= 0),
    model            text,
    tenant           text,
    actor            text,
    claim_id         text,
    settled_inr      numeric(14,4) CHECK (settled_inr >= 0),
    settled_requests integer       CHECK (settled_requests >= 0),
    basis            text          CHECK (basis IN ('held', 'measured')),
    created_at       timestamptz   NOT NULL DEFAULT now(),
    settled_at       timestamptz
);

CREATE INDEX IF NOT EXISTS model_spend_holds_live_idx
    ON model_spend_holds (day) WHERE settled_at IS NULL;

ALTER TABLE model_spend ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_spend FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS global_access ON model_spend;
CREATE POLICY global_access ON model_spend USING (true);

ALTER TABLE model_spend_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_spend_holds FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS global_access ON model_spend_holds;
CREATE POLICY global_access ON model_spend_holds USING (true);

COMMENT ON TABLE model_spend IS
    'Model spend counters per (scope, period, day), rupees; shared across instances.';
COMMENT ON TABLE model_spend_holds IS
    'Model spend reservations and their settlement receipts; ids and amounts only.';

COMMIT;
