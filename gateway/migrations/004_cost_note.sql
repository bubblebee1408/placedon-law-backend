-- 004_cost_note.sql — why a step's cost is null.
--
-- 003 added run_steps.cost_inr and every Azure step recorded 0.00, which was false: those
-- calls bill Azure for Students credit. The number came from router.estimate_inr, which is
-- 0.0 for Azure and says in its own comment that this is "zero against MONTHLY_CAP_INR,
-- NOT a claim that the call is free" -- and a recorded 0.00 IS that claim.
--
-- Costs are now derived from the tokens a call reported, against backend/azure_pricing.py.
-- When no verified price exists for a deployment the cost is NULL and cost_note says so.
-- NULL therefore has two readings and the note distinguishes them:
--
--   "UNPRICED: ..."         a call happened and we cannot price it
--   "no call was made ..."  no model ran on this step at all
--
-- A zero would have collapsed both into "free", which neither is.

BEGIN;

ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS cost_note text;

-- The rows already written under 003 carry the falsehood, and the constraint below
-- REFUSED to be added over them -- which is the guard working on real data before it was
-- ever asked to guard anything. They are corrected to UNPRICED with a note saying why,
-- rather than deleted: they are a true record that a call happened, and only the cost was
-- wrong.
UPDATE run_steps
   SET cost_inr  = NULL,
       cost_note = 'UNPRICED: recorded as 0.00 before backend/azure_pricing.py existed. '
                   'The call was made and billed to Azure for Students credit; the amount '
                   'was never measured and 0.00 was router.estimate_inr''s rupee-cap '
                   'figure, not a price.'
 WHERE provider IN ('azure', 'anthropic')
   AND cost_inr = 0;

-- A billed provider may not claim a call was free. The database enforces what
-- backend/azure_pricing.check_recordable enforces in Python, because the application is
-- not the only thing that can write a row.
ALTER TABLE run_steps DROP CONSTRAINT IF EXISTS run_steps_billed_never_zero;
ALTER TABLE run_steps ADD CONSTRAINT run_steps_billed_never_zero
    CHECK (provider IS NULL OR provider NOT IN ('azure', 'anthropic') OR cost_inr <> 0);

COMMIT;
