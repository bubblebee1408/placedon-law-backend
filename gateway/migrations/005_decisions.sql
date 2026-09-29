-- 005_decisions.sql — the human gate, stored as labelled data.
--
-- PLAN_23 layer 9 and rule 5: "every human decision is stored as labelled data." A reviewer's
-- judgement is the scarcest input this system has. Discarding it is how a product sits at
-- n=0 human labels for a year while collecting thousands of them and throwing each away the
-- moment the screen refreshes.
--
-- ## Why a reason is NOT NULL, and why a blank one is refused in SQL too
--
-- An approval with no reason is not a label. It records that somebody clicked, which is the
-- automation-bias failure Goddard et al. (JAMIA 2012) describe and which PLAN_23 §1.8 exists
-- to prevent. The API refuses one; this refuses it again, because a second writer -- a
-- backfill, a fixture, a future worker -- reaches the table and not the API.
--
-- MIN_REASON_CHARS is 10 here and in gateway/verbs.py. "ok", "fine" and "yes" are not
-- reasons, and a label whose text is "ok" teaches a future evaluation nothing at all.
--
-- ## Why quoted_span is stored, and what it is NOT
--
-- `propositions` deliberately holds offsets and no text, so it cannot become a second,
-- divergent copy of evidence. A decision is a different object: it records WHAT THE REVIEWER
-- WAS LOOKING AT when they decided. That text is supplied by the surface that displayed it,
-- and it is stored verbatim for that reason -- not re-derived here.
--
-- **So it is an attestation, not independently verified evidence**, and it must not be cited
-- as though the server had checked it. It is checkable later against the stored document by
-- sha256, and doing that check is not in O1.
--
-- STATUS: applied 2026-09-30 by scripts/rls_integration.py.

BEGIN;

CREATE TABLE IF NOT EXISTS decisions (
    decision_id  uuid PRIMARY KEY,
    run_id       uuid NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
    -- Which item in that run. The same string `propositions.source_ref` carries, so a
    -- decision joins to the thing it was about: 'playbook:NDA-08', 'ss:T1.2'.
    item_ref     text NOT NULL,
    decision     text NOT NULL,
    reason       text NOT NULL,
    -- What the reviewer was shown. See the header: an attestation, not re-derived evidence.
    quoted_span  text NOT NULL,
    actor_id     uuid NOT NULL,
    decided_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT decisions_verdict_known CHECK (decision IN ('APPROVED', 'REJECTED')),
    -- No third state. "deferred" would be the absence of a row, and a row saying a human
    -- did not decide is a label with nothing in it.
    CONSTRAINT decisions_reason_substantive CHECK (length(btrim(reason)) >= 10),
    CONSTRAINT decisions_span_present CHECK (length(btrim(quoted_span)) >= 1),
    CONSTRAINT decisions_item_ref_shape CHECK (item_ref ~ '^[a-z_]+:[A-Za-z0-9._-]+$'),
    -- One decision per item per run. A reviewer changing their mind writes a NEW decision
    -- for a NEW run; overwriting would destroy the label that was there, and the label is
    -- the point of the table.
    CONSTRAINT decisions_one_per_item UNIQUE (run_id, item_ref)
);

CREATE INDEX IF NOT EXISTS decisions_by_run ON decisions (run_id);

ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON decisions;
CREATE POLICY tenant_isolation ON decisions USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMIT;
