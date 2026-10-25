-- 029_vault_partial.sql — a vault document can be PARTIAL: stored and searchable, with the
-- pages that had no text layer NAMED.
--
-- agents/vault_ingest.py has returned state PARTIAL with `failed_pages` since A1 item 6,
-- but 020's CHECK admitted only PENDING / INGESTED / CANNOT_READ / DELETED, so the write
-- was refused and the path could never run. The frontend now sends a PDF's pages joined
-- by form feeds; a page with no text layer (a scanned signature page, a stamped annexure)
-- is a failed page, and the document must say it is incomplete rather than look whole.
--
-- Additive: widens one CHECK, rewrites no row, removes nothing.

BEGIN;

ALTER TABLE vault_documents DROP CONSTRAINT IF EXISTS vault_documents_state_check;
ALTER TABLE vault_documents ADD CONSTRAINT vault_documents_state_check
    CHECK (state IN ('PENDING', 'INGESTED', 'PARTIAL', 'CANNOT_READ', 'DELETED'));

COMMIT;
