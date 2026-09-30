-- 009_source_documents.sql — public material we have fetched, hashed once and shared.
--
-- PLAN_26 §4: "public material goes into one hash-stamped `source_documents` table, shared
-- across tenants because it is public; caching follows each source's terms record."
--
-- ## NOT tenant-scoped, and that is the decision
--
-- Every other table in this schema carries `tenant` under FORCE ROW LEVEL SECURITY. This
-- one does not, because a SEBI circular is not anybody's private document and storing one
-- copy per tenant would mean the same bytes under N hashes, N fetches against a source with
-- a courtesy delay, and no way to answer "have we already read this".
--
-- The safety argument is the tier: nothing at tier CLIENT may ever be written here. A
-- client contract in a cross-tenant table is the worst bug this schema could have, so the
-- CHECK below refuses the tier rather than trusting the writer, and the client path keeps
-- using `documents` (001) under its own RLS.
--
-- ## Nothing may be written here today
--
-- S0 read every source's terms and **not one of the seven permits caching**:
--
--     rbi           PROHIBITED  "Except as set forth below, caching and links to, and the
--                               framing of this Web Site or any of the contents are
--                               prohibited."
--     sebi          OPEN        reproduction is gated on emailing for permission; caching
--                               is not addressed at all
--     indiankanoon  OPEN        the terms never say whether WE may store what we fetch
--     egazette, data_gov_in, bse, nse
--                   OPEN        no terms page could be read
--
-- `checker/sources/terms.may_cache()` therefore returns False for all seven, and this table
-- is created empty and stays empty until an owner reads a term or obtains a permission.
-- **That is why the table exists now rather than later**: the shape of the permission is
-- the thing being recorded, and `terms_basis` below is the column that makes a row
-- indefensible without one.
--
-- A migration for a table nothing may write to looks like dead weight. The alternative is
-- a connector landing later next to no storage design and inventing one inline, which is
-- how a client contract ends up in a shared table.
--
-- ## Columns
--
-- sha256        the identity. The bytes' digest, as `documents` (001) and
--               `documents.upload` already do: "the identity IS the hash, not a counter".
-- tier          OFFICIAL_LIVE | LICENSED | COMPANY_FACT. HELD is the corpus in git and
--               CLIENT belongs in `documents`; both are refused by the CHECK.
-- source_id     the key into checker/sources/terms.py. Not free text: a row whose terms
--               cannot be looked up cannot be shown to have been lawfully stored.
-- url           where it was fetched from. https only, and NOT NULL: a cached public
--               document with no address is unverifiable.
-- fetched_at    when. timestamptz, so an IST read is never re-read as UTC.
-- content_type  what the server said it was, kept beside the bytes because
--               `payload_refusal()`'s verdict is only meaningful with both.
-- payload_kind  what we ASKED for and checked (PDF/JSON/XML/HTML/TEXT/DER). A 200 of HTML
--               where a PDF was expected never becomes a row.
-- bytes         the material. BYTEA, not TEXT: a Gazette PDF is not text, and decoding it
--               with errors="replace" produced mojibake that looked like a short document.
-- attribution   the source's own required words, copied from the terms record at write
--               time. NOT NULL for LICENSED and COMPANY_FACT (CHECK below), because Indian
--               Kanoon's clause requires attribution for RAG context and not only display.
-- terms_basis   the clause that PERMITTED this row, verbatim. Not a boolean, not a date:
--               the words. An empty one is refused, which is what keeps the table empty
--               while every source's caching clause is OPEN or PROHIBITED.

CREATE TABLE IF NOT EXISTS source_documents (
    sha256        text        PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    tier          text        NOT NULL
                              CHECK (tier IN ('OFFICIAL_LIVE', 'LICENSED', 'COMPANY_FACT')),
    source_id     text        NOT NULL CHECK (length(btrim(source_id)) > 0),
    url           text        NOT NULL CHECK (url LIKE 'https://%'),
    fetched_at    timestamptz NOT NULL,
    content_type  text        NOT NULL DEFAULT '',
    payload_kind  text        NOT NULL
                              CHECK (payload_kind IN ('PDF','JSON','XML','HTML','TEXT','DER')),
    bytes         bytea       NOT NULL,
    attribution   text        NOT NULL DEFAULT '',
    terms_basis   text        NOT NULL,

    -- The permission must be present in words. A row with no quoted basis is a row nobody
    -- can defend, and "the terms were fine" is not a basis.
    CONSTRAINT terms_basis_quoted CHECK (length(btrim(terms_basis)) >= 20),

    -- Attribution is required exactly where the terms require it.
    CONSTRAINT attribution_when_required CHECK (
        tier NOT IN ('LICENSED', 'COMPANY_FACT') OR length(btrim(attribution)) > 0
    ),

    -- A fetch cannot have happened in the future. Clock slack matches
    -- checker/provenance.CLOCK_SLACK (1 day) rather than being invented here.
    CONSTRAINT fetched_not_future CHECK (fetched_at <= now() + interval '1 day')
);

CREATE INDEX IF NOT EXISTS source_documents_source_idx ON source_documents (source_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS source_documents_url_idx    ON source_documents (url);

COMMENT ON TABLE source_documents IS
  'Public fetched material, hashed, shared across tenants. CLIENT and HELD are refused by '
  'CHECK: client documents belong in documents (001) under FORCE RLS, and HELD is the git '
  'corpus. Empty until a source permits caching -- see checker/sources/terms.may_cache().';
COMMENT ON COLUMN source_documents.terms_basis IS
  'The clause that permitted this row, verbatim. Not a boolean: the words.';
