-- 025_draft_inbox_idx.sql — bounded keyset reads for the tenant Drafts inbox.
--
-- The inbox orders by updated_at DESC, draft_id DESC and always runs under the tenant RLS
-- policy. Keeping the tenant and both ordering keys in the index avoids scanning and sorting
-- the full tenant draft set for each small page.

BEGIN;

CREATE INDEX IF NOT EXISTS drafts_inbox_idx
    ON drafts (tenant_id, updated_at DESC, draft_id DESC);

COMMIT;
