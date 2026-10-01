-- 010_conversations.sql — the chat layer's two tables. Tenant-scoped, FORCE RLS.
--
-- C2. What a chat UI needs that `runs` (002) does not give it: a thread, and the messages
-- in it in order. A run is one unit of work; a conversation is the thing a lawyer comes
-- back to on Tuesday.
--
-- Numbered 010 and not 009. 009 was taken by `source_documents` on the branch that merged
-- as PR #25 while this work was in progress, and this file was written against a tree that
-- already had it. The repository has done this the other way twice ("006 was taken twice,
-- so T0's is now 008") and the cost each time was a merge that looked clean and applied two
-- different files under one number.
--
-- ## Both tables are tenant-scoped, and both get all three declarations
--
--     ALTER TABLE x ENABLE ROW LEVEL SECURITY;   -- exempts the table OWNER
--     ALTER TABLE x FORCE  ROW LEVEL SECURITY;   -- and now it does not
--
-- `gateway/schema.py` derives the tenant-scoped set FROM the SQL -- every CREATE TABLE
-- carrying a tenant_id -- so these two are in scope for that check the moment they exist,
-- whether or not anyone remembered to list them. `scripts/rls_integration.py` adds them to
-- TENANT_TABLES, which is what puts them through the full proof: A sees its own rows and
-- none of B's; with the policy dropped it fails CLOSED; with RLS disabled B's rows APPEAR,
-- which is what shows the check measures the protection rather than an empty table.
--
-- ## messages.role, and why there is no 'system'
--
-- 'user' and 'assistant' only. A system prompt is not a message in a conversation: it is
-- part of how a step was executed, it belongs to the run, and putting it here would put
-- untrusted document text and our own instructions in the same column with a flag to tell
-- them apart. `checker/prompt_safety.py` exists because that distinction has to be
-- structural.
--
-- ## envelope
--
-- The assistant's reply, stored as the versioned answer envelope
-- (`gateway/schemas/answer_envelope.v1.json`) rather than as prose. A conversation
-- re-opened next week must render the same citations, body statuses and file states it
-- rendered the first time, and prose cannot be re-rendered into a source panel.
--
-- NULL means the reply has not arrived: `conversation.send` returns a run_id at once for
-- long work, and the envelope is written when the run finishes. NOT '{}', which would
-- claim an empty answer.
--
-- ## run_id is the link, and it is nullable
--
-- A message may have no run: NEEDS_CLARIFICATION runs nothing, and neither does a user
-- message. ON DELETE SET NULL rather than CASCADE -- deleting a run must not delete the
-- conversation that asked for it, because the question was still asked.

BEGIN;

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id uuid        PRIMARY KEY,
    tenant_id       uuid        NOT NULL REFERENCES tenants(tenant_id),
    actor_id        uuid        REFERENCES actors(actor_id),
    title           text        NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    message_id      uuid        PRIMARY KEY,
    conversation_id uuid        NOT NULL REFERENCES conversations(conversation_id)
                                ON DELETE CASCADE,
    tenant_id       uuid        NOT NULL REFERENCES tenants(tenant_id),
    ordinal         integer     NOT NULL,
    role            text        NOT NULL CHECK (role IN ('user', 'assistant')),
    text            text        NOT NULL DEFAULT '',
    file_ids        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    task            text,
    run_id          uuid        REFERENCES runs(run_id) ON DELETE SET NULL,
    envelope        jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),

    -- One ordinal per conversation: the order a conversation is read in is not a detail
    -- the application may get wrong twice.
    CONSTRAINT messages_ordinal_unique UNIQUE (conversation_id, ordinal),

    -- A user message never carries an envelope, and an assistant message never carries
    -- file_ids. Enforced here because a second writer reaches the table and not the API --
    -- the same reasoning 005's reason check and 008's quote_viewed check are built on.
    CONSTRAINT messages_user_has_no_envelope CHECK (
        role <> 'user' OR envelope IS NULL
    ),
    CONSTRAINT messages_assistant_has_no_files CHECK (
        role <> 'assistant' OR file_ids = '[]'::jsonb
    ),

    -- An envelope is an object, never a list or a bare string. Same shape of check as
    -- 008's runs_law_versions_object.
    CONSTRAINT messages_envelope_object CHECK (
        envelope IS NULL OR jsonb_typeof(envelope) = 'object'
    ),
    CONSTRAINT messages_file_ids_array CHECK (jsonb_typeof(file_ids) = 'array')
);

CREATE INDEX IF NOT EXISTS messages_thread_idx
    ON messages (conversation_id, ordinal);
CREATE INDEX IF NOT EXISTS conversations_tenant_idx
    ON conversations (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS messages_run_idx ON messages (run_id);

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE  ROW LEVEL SECURITY;
ALTER TABLE messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages      FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON conversations;
CREATE POLICY tenant_isolation ON conversations USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON messages;
CREATE POLICY tenant_isolation ON messages USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE conversations IS
  'A chat thread. Tenant-scoped under FORCE RLS; proved by scripts/rls_integration.py.';
COMMENT ON COLUMN messages.envelope IS
  'The assistant reply as answer_envelope.v1. NULL = the reply has not arrived yet, which '
  'is not the same as an empty answer.';
COMMENT ON COLUMN messages.run_id IS
  'Nullable: NEEDS_CLARIFICATION runs nothing. ON DELETE SET NULL, because deleting a run '
  'must not delete the conversation that asked for it.';

COMMIT;
