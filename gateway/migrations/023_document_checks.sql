-- 023_document_checks.sql — the outcome of a Document Check, one row per CHECK.
--
-- T3 move 10. `document.verify` (move 8) answers "was this signed"; `checker/doc_validity`
-- (move 9) answers "is it still in force". This table records what we TOLD someone, and the
-- action we told them to take.
--
-- Architect record: .claude/loops/DECISION_document_checks_table.md
--
-- NUMBERED 023, and 022 is missing on purpose. `022_grid_budget_state.sql` belongs to
-- `claude/overnight-a` (PR #67, still open). Branches are cut from `origin/main` and never
-- stacked, so it is not on this branch, and reusing 022 would put two different migrations at
-- one number the moment #67 merges. The gap closes when it does.
--
-- ## One row per CHECK, never updated in place
--
-- A certificate valid in March is expired in October: the same bytes produce a different
-- action, and the answer changes without the document changing. A table that overwrote would
-- answer "what is the status" and lose "what did we tell them in March" -- which is the
-- question that matters when a client asks why they were not warned. `runs` already works
-- this way and `decisions` copies its run's law_versions at the moment it is made (008); an
-- append-only check history is the same shape as the audit records around it.
--
-- RENEW_BY rows feed `calendar.upcoming`. With one row per document, a deadline the calendar
-- showed last week and does not show today would be indistinguishable from a bug.

BEGIN;

CREATE TABLE IF NOT EXISTS document_checks (
    check_id     uuid        PRIMARY KEY,
    tenant_id    uuid        NOT NULL REFERENCES tenants (tenant_id),
    document_id  uuid        NOT NULL,
    checked_at   timestamptz NOT NULL DEFAULT now(),
    -- The date the validity question was asked ABOUT. NOT `checked_at`: a lawyer asks "was
    -- this good on the day of the meeting", and recording only the wall clock would make a
    -- correct answer about a past date look like a stale answer about today.
    as_of        date        NOT NULL,

    -- From checker/doc_verification.compute_overall().
    verification_status text NOT NULL
        CHECK (verification_status IN ('COMPLETE_VERIFICATION',
                                       'INCOMPLETE_VERIFICATION',
                                       'VERIFICATION_FAILED')),
    -- From checker/doc_validity.STATUSES.
    validity_status text NOT NULL
        CHECK (validity_status IN ('CURRENT', 'EXPIRES_ON', 'EXPIRED',
                                   'SUPERSEDED', 'REVOKED', 'NOT_DETERMINED')),
    action text NOT NULL
        CHECK (action IN ('KEEP', 'RENEW_BY', 'REPLACE', 'REMOVE', 'NEEDS_LAWYER')),

    -- An action with no reason is a verdict nobody can check, and this table is read months
    -- later by someone who was not here. The CHECK is in the DATABASE and not only in Python
    -- because a second writer reaches the table and not the API -- the same reasoning
    -- 005_decisions.sql gives for its own reason check.
    action_reason text NOT NULL CHECK (length(btrim(action_reason)) >= 20),

    -- NULL is "no end date was derived", never "no expiry". `doc_validity` returns
    -- NOT_DETERMINED in that case and its reason says why.
    expires_on date,
    renew_by   date,

    -- Which held text the validity rule rested on: {repo-relative path: git blob id}, the
    -- same identity as runs.law_versions (008) and public_only.Origin.blob, so recall and
    -- the answer cache compare one thing. NULL means NOT RECORDED.
    law_versions jsonb,

    CONSTRAINT document_checks_law_versions_object
        CHECK (law_versions IS NULL OR jsonb_typeof(law_versions) = 'object'),

    -- A RENEW_BY with no date is a deadline the calendar cannot show. A date on a KEEP is a
    -- deadline that would appear for a document needing nothing. Both directions, so neither
    -- can be written.
    CONSTRAINT document_checks_renew_by_iff_renew
        CHECK ((action = 'RENEW_BY') = (renew_by IS NOT NULL)),

    -- The done-when, restated in the database: an EXPIRED, REVOKED or SUPERSEDED document is
    -- never KEEP, and a verification that FAILED is never KEEP. Python decides the action;
    -- this refuses to store a contradiction, because the rule is worth more than the one
    -- code path that currently applies it.
    CONSTRAINT document_checks_keep_requires_force
        CHECK (action <> 'KEEP' OR (validity_status IN ('CURRENT', 'EXPIRES_ON')
                                    AND verification_status <> 'VERIFICATION_FAILED'))
);

-- The calendar's query: this tenant's outstanding renewals, soonest first.
CREATE INDEX IF NOT EXISTS document_checks_renew_by_idx
    ON document_checks (tenant_id, renew_by)
    WHERE renew_by IS NOT NULL;

-- "What did we last say about this document?"
CREATE INDEX IF NOT EXISTS document_checks_document_idx
    ON document_checks (tenant_id, document_id, checked_at DESC);

ALTER TABLE document_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_checks FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON document_checks;
CREATE POLICY tenant_isolation ON document_checks USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON COLUMN document_checks.as_of IS
  'The date the validity question was asked ABOUT, not when it was asked. A correct answer '
  'about a past date is not a stale answer about today.';
COMMENT ON COLUMN document_checks.expires_on IS
  'NULL means no end date was DERIVED -- never that the document does not expire. '
  'checker/doc_validity returns NOT_DETERMINED in that case and names the reason.';
COMMENT ON CONSTRAINT document_checks_keep_requires_force ON document_checks IS
  'An expired, revoked or superseded document is never KEEP, and neither is one whose '
  'signature verification FAILED. Enforced here as well as in Python because a second '
  'writer reaches the table and not the API.';

COMMIT;
