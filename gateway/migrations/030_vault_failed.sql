-- 030_vault_failed.sql — a vault document whose ingest gave up is FAILED, with the reason.
--
-- When an ingest job used up its attempts (gateway/jobs.py MAX_ATTEMPTS) the job went DEAD
-- and its run FAILED, but the document stayed PENDING: "queued; not searchable yet" for a
-- document nothing would ever read again. gateway/worker.py now marks it FAILED, and
-- `vault.retry` (or uploading the same bytes again) puts it back to PENDING with its job
-- requeued.
--
-- `failure_reason` is set exactly when the state is FAILED, so a FAILED document always
-- says why and a retried one does not keep a stale reason.
--
-- Additive: one column, one widened CHECK, one new CHECK. No row is rewritten or removed.

BEGIN;

ALTER TABLE vault_documents ADD COLUMN IF NOT EXISTS failure_reason text;

ALTER TABLE vault_documents DROP CONSTRAINT IF EXISTS vault_documents_state_check;
ALTER TABLE vault_documents ADD CONSTRAINT vault_documents_state_check
    CHECK (state IN ('PENDING', 'INGESTED', 'PARTIAL', 'CANNOT_READ', 'DELETED', 'FAILED'));

ALTER TABLE vault_documents DROP CONSTRAINT IF EXISTS vault_documents_failed_has_reason;
ALTER TABLE vault_documents ADD CONSTRAINT vault_documents_failed_has_reason
    CHECK ((state = 'FAILED') = (coalesce(failure_reason, '') <> ''));

COMMIT;
