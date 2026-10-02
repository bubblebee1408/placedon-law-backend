-- 020_vault.sql — twenty thousand documents, and what is known about each.
--
-- V1. `documents` (001) holds a hash, a name and a byte count for things uploaded to a
-- conversation. A vault is a different thing: files a firm keeps, filed to matters,
-- searched across, and deleted on request. It gets its own tables rather than more columns
-- on `documents`, because the lifecycle is different -- a vault document is INGESTED by a
-- job, classified, chunked and tagged, and every one of those can fail on its own.
--
-- ## state is a lifecycle, not a boolean
--
--   PENDING      the bytes are stored and nothing has read them yet
--   INGESTED     text was extracted; text_chars says how much
--   CANNOT_READ  it was read and there is no text layer -- a scan. NOT a failure of
--                ingestion, and not an empty document: the distinction decides whether
--                OCR is the next step or whether the file is simply blank.
--   DELETED      the row stays, the bytes are gone. See below.
--
-- ## Deletion keeps the row
--
-- A firm that asks us to delete a document is asking for the BYTES to go. The row stays
-- with `deleted_at` set, because "we never had it" and "we had it and destroyed it on 4
-- March" are different answers to a regulator, and only one of them is true. The row
-- carries no text after deletion -- `text_chars` and the chunks go -- so nothing
-- searchable survives.
--
-- ## ocr_state is NEEDED or BLOCKED, never silently skipped
--
-- Textract is BLOCKED until AWS. A scanned document therefore sits at ocr_state='BLOCKED'
-- and is VISIBLE as such, rather than being INGESTED with no text and looking identical to
-- a blank page. The vault's search tells the user how many of its documents it cannot read.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-020 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS).

BEGIN;

CREATE TABLE IF NOT EXISTS vault_documents (
    document_id uuid        PRIMARY KEY,
    tenant_id   uuid        NOT NULL REFERENCES tenants(tenant_id),
    matter_id   uuid        REFERENCES matters(matter_id),
    sha256      text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    name        text        NOT NULL CHECK (length(btrim(name)) > 0),
    byte_count  integer     NOT NULL CHECK (byte_count >= 0),
    state       text        NOT NULL DEFAULT 'PENDING'
                            CHECK (state IN ('PENDING', 'INGESTED', 'CANNOT_READ',
                                             'DELETED')),
    -- From the fixed-list classifier. 'unknown' is a real class, never NULL-as-unknown:
    -- NULL means NOT YET CLASSIFIED, which is a different fact.
    doc_class   text,
    class_reason text,
    -- How much text was extracted. NULL means not extracted yet; 0 means read and empty,
    -- which is why the two are not the same value.
    text_chars  integer     CHECK (text_chars IS NULL OR text_chars >= 0),
    ocr_state   text        NOT NULL DEFAULT 'NOT_NEEDED'
                            CHECK (ocr_state IN ('NOT_NEEDED', 'NEEDED', 'BLOCKED',
                                                 'DONE')),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    ingested_at timestamptz,
    deleted_at  timestamptz,

    -- Dedupe is per TENANT, not global: two firms may hold the same standard form, and
    -- one firm's deletion must not remove the other's document.
    CONSTRAINT vault_documents_tenant_sha UNIQUE (tenant_id, sha256),
    -- A classified document says WHY. A bare class in a list of twenty thousand is a
    -- number nobody can check.
    CONSTRAINT vault_documents_class_has_reason CHECK (
        doc_class IS NULL OR length(btrim(coalesce(class_reason, ''))) > 0),
    -- Deleted means the bytes are gone, so nothing searchable may remain.
    CONSTRAINT vault_documents_deleted_has_no_text CHECK (
        state <> 'DELETED' OR text_chars IS NULL)
);

-- The searchable unit. One row per chunk, so BM25 scores a passage rather than a file,
-- and a hit can be shown with the words around it.
CREATE TABLE IF NOT EXISTS vault_chunks (
    document_id uuid    NOT NULL REFERENCES vault_documents(document_id) ON DELETE CASCADE,
    tenant_id   uuid    NOT NULL REFERENCES tenants(tenant_id),
    ordinal     integer NOT NULL CHECK (ordinal >= 0),
    text        text    NOT NULL CHECK (length(btrim(text)) > 0),
    PRIMARY KEY (document_id, ordinal)
);

-- CUAD clause tags. The QUOTE is required: a tag with no span is an assertion about a
-- document that nobody can check against it, which is the whole failure mode this
-- repository exists to refuse.
CREATE TABLE IF NOT EXISTS vault_tags (
    document_id uuid    NOT NULL REFERENCES vault_documents(document_id) ON DELETE CASCADE,
    tenant_id   uuid    NOT NULL REFERENCES tenants(tenant_id),
    tag         text    NOT NULL CHECK (length(btrim(tag)) > 0),
    quote       text    NOT NULL CHECK (length(btrim(quote)) >= 8),
    span_start  integer CHECK (span_start IS NULL OR span_start >= 0),
    span_end    integer CHECK (span_end IS NULL OR span_end >= 0),
    PRIMARY KEY (document_id, tag, quote)
);

CREATE INDEX IF NOT EXISTS vault_documents_matter_idx
    ON vault_documents (tenant_id, matter_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS vault_documents_state_idx
    ON vault_documents (tenant_id, state);
CREATE INDEX IF NOT EXISTS vault_chunks_tenant_idx ON vault_chunks (tenant_id);

ALTER TABLE vault_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_documents FORCE  ROW LEVEL SECURITY;
ALTER TABLE vault_chunks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_chunks    FORCE  ROW LEVEL SECURITY;
ALTER TABLE vault_tags      ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_tags      FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON vault_documents;
CREATE POLICY tenant_isolation ON vault_documents USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON vault_chunks;
CREATE POLICY tenant_isolation ON vault_chunks USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON vault_tags;
CREATE POLICY tenant_isolation ON vault_tags USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON COLUMN vault_documents.state IS
  'CANNOT_READ means read with no text layer -- a scan. It is NOT a failed ingestion and '
  'NOT a blank page, and the difference decides whether OCR is next.';
COMMENT ON COLUMN vault_documents.deleted_at IS
  'The row survives deletion; the bytes and the chunks do not. "We never had it" and "we '
  'had it and destroyed it on 4 March" are different answers to a regulator.';
COMMENT ON COLUMN vault_documents.text_chars IS
  'NULL means NOT EXTRACTED. 0 means read and empty. They are different facts.';

COMMIT;
