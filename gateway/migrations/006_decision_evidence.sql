-- 006_decision_evidence.sql — what a human decision was made against, and whether the quote
-- was seen. PLAN_23 O1, layer 9 (the human gate) and layer 10 (record the law versions used).
--
-- ## law_versions
--
-- {repo-relative path: git blob id} of the held text a run READ: the statute sections an
-- answer cited, the SS-1/SS-2 texts a filing was checked against, the playbook a contract
-- was reviewed under. The same identity `public_only.Origin.blob` carries, so O7 (recall)
-- and O9 (the answer cache) compare one thing.
--
-- NULL means NOT RECORDED -- every run written before this migration, and every run that
-- served no item. It is deliberately not '{}', which would claim the run read no law.
--
-- A decision copies its run's map when it is made. The API never accepts one from the
-- caller: the versions a decision was made against are the ones its finding was computed
-- against, and a reviewer cannot know them.
--
-- ## quote_viewed
--
-- PLAN_23 §1.8 (Goddard et al., JAMIA 2012, automation bias): a finding may not be ACCEPTED
-- unless the reviewer was shown the quote. The API refuses such an approval; the CHECK
-- below refuses it again, because a second writer reaches the table and not the API -- the
-- same reasoning as 005's reason check.
--
-- It is an ATTESTATION by the surface that displayed the quote, exactly as quoted_span is.
-- It is not proof a person read anything; O6's review UI is what makes it true.
--
-- Rows written before this migration default to false. None of them is an APPROVED row
-- with a verified view, so the CHECK is added NOT VALID -- it binds every new row and
-- makes no retroactive claim about the old ones -- and then VALIDATED, which succeeds only
-- if no existing approval would violate it. If validation fails, the migration fails and
-- the pre-existing approvals must be looked at by a person, not defaulted.
--
-- STATUS: applied 2026-09-30 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database: 77 checks, 0 failures. NOT yet applied to placedon_dev, whose earlier seed
-- approvals predate quote_viewed -- VALIDATE will refuse them, by design.

BEGIN;

ALTER TABLE runs      ADD COLUMN IF NOT EXISTS law_versions jsonb;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS law_versions jsonb;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS quote_viewed boolean NOT NULL DEFAULT false;

ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_law_versions_object;
ALTER TABLE runs ADD CONSTRAINT runs_law_versions_object
    CHECK (law_versions IS NULL OR jsonb_typeof(law_versions) = 'object');
ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_law_versions_object;
ALTER TABLE decisions ADD CONSTRAINT decisions_law_versions_object
    CHECK (law_versions IS NULL OR jsonb_typeof(law_versions) = 'object');

ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_approval_saw_quote;
ALTER TABLE decisions ADD CONSTRAINT decisions_approval_saw_quote
    CHECK (decision <> 'APPROVED' OR quote_viewed) NOT VALID;
ALTER TABLE decisions VALIDATE CONSTRAINT decisions_approval_saw_quote;

COMMIT;
