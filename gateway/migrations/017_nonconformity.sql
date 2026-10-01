-- 017_nonconformity.sql — how hard the system had to work for this answer.
--
-- CAL-1's missing input, decided by the founder on 2026-10-02:
--
--     (1 - share of sentences with a byte-matched quote AND passed entailment)
--     + 0.5 * number of cascade escalations
--
-- `checker/calibration.nonconformity()` is the one function that computes it. Both terms
-- are "the system had to work harder, or had less to stand on" -- neither is a model's
-- opinion of itself, which is what makes the score admissible at all (PLAN_23 §1.5), and
-- what keeps C4 intact: this is not a confidence and it never reaches an answer.
--
-- ## NULL is the normal case today, and that is a finding
--
-- The score needs sentences that are byte-matched AND entailed. The `ask` path builds its
-- answer through `checker/lawyer_summary.py`, which produces TRACED and says in terms that
-- "TRACED IS NOT ENTAILMENT" -- its ENTAILED verdict is declared and NEVER RETURNED. The
-- entailment gate runs in `checker/model_cascade.py`, on a different path.
--
-- So a run records a score when both inputs exist and NULL when they do not, with
-- `nonconformity_note` saying which. Writing a score from the TRACED count alone would be
-- a different measurement under the same name, and it would be the one every threshold is
-- later computed from.
--
-- A score of 0 is meaningful (every sentence supported, no escalation) and is NOT the same
-- as NULL, which is why the column is nullable rather than defaulted.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-017 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 258 checks, 0 failures, then the database dropped.

BEGIN;

ALTER TABLE runs ADD COLUMN IF NOT EXISTS nonconformity      numeric(8, 4);
ALTER TABLE runs ADD COLUMN IF NOT EXISTS nonconformity_note text;

-- The score is a distance, never negative. The upper end is unbounded on purpose: three
-- escalations alone reach 1.5, and clamping it to 1 would make "worse than total lexical
-- failure" indistinguishable from it.
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_nonconformity_not_negative;
ALTER TABLE runs ADD CONSTRAINT runs_nonconformity_not_negative
    CHECK (nonconformity IS NULL OR nonconformity >= 0);

-- A score always says what it was computed from, and a NULL always says why there is none.
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_nonconformity_has_note;
ALTER TABLE runs ADD CONSTRAINT runs_nonconformity_has_note
    CHECK (nonconformity IS NULL OR length(btrim(coalesce(nonconformity_note, ''))) > 0);

COMMENT ON COLUMN runs.nonconformity IS
  'CAL-1 nonconformity: (1 - share of sentences byte-matched AND entailed) + 0.5 * '
  'escalations. NULL means NOT COMPUTED -- usually because the path produced TRACED but '
  'no entailment verdict. It is not a confidence and may never reach an answer (C4).';

COMMIT;
