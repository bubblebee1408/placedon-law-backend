-- 003_step_provenance.sql — where a step's model ran, and what it cost.
--
-- PLAN_22 D3 permits client documents only to endpoints whose hosting REGION is confirmed.
-- A region recorded in a deployment note is a region nobody checks; recorded on the step,
-- it answers "where did this document go" from the trace itself, per call, for ever.
--
-- cost_inr is numeric and nullable. NULL means "no model was called on this step" (intake,
-- playbook) and is not the same as 0.00, which means a call was made and estimated at zero
-- against MONTHLY_CAP_INR — Azure credit is a separate pot no counter here watches.

BEGIN;

ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS provider text;
ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS region   text;
ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS cost_inr numeric(12, 4)
    CHECK (cost_inr IS NULL OR cost_inr >= 0);

COMMIT;
