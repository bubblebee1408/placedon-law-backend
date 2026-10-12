-- Keep answer_envelope.v1 immutable; turn metadata is an independently versioned sibling.
BEGIN;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS metadata jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS payload_digest text;
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_metadata_object;
ALTER TABLE messages ADD CONSTRAINT messages_metadata_object CHECK
    (metadata IS NULL OR jsonb_typeof(metadata) = 'object');
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_request_shape;
ALTER TABLE messages ADD CONSTRAINT messages_request_shape CHECK
    ((request_id IS NULL AND payload_digest IS NULL) OR
     (request_id IS NOT NULL AND payload_digest IS NOT NULL
      AND role = 'assistant' AND length(request_id) BETWEEN 8 AND 128
      AND payload_digest ~ '^[0-9a-f]{64}$'));
CREATE UNIQUE INDEX IF NOT EXISTS messages_tenant_request_unique
    ON messages (tenant_id, request_id) WHERE request_id IS NOT NULL;
-- Existing FORCE RLS on messages remains in force. No new tenant table is introduced.
COMMIT;
