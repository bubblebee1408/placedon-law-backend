-- 014_answer_cache.sql — answers that may be served again, and only while they are true.
--
-- PLAN_23 O9. A cache in a product whose claim is that every answer cites the provision it
-- rests on. So the stored thing is not "an answer we gave" but "an answer we can still
-- show is true", and the row carries everything needed to re-check that: the citations, and
-- the content key over their provision hashes. `checker/answer_cache.py` holds the rules;
-- this holds the rows.
--
-- ## Two keys, because the brief's key cannot be a lookup
--
-- PLAN_23 gives the key as (normalised question, task, as_of, sha256 of every cited
-- provision, sources). The cited provisions are known only AFTER the answer exists, so a
-- lookup keyed on them could never hit. Split:
--
--   lookup_key   (normalised question, task, as_of, sources)  -- the PRIMARY KEY, queried
--   content_key  lookup_key + the sorted provision hashes     -- the full identity, checked
--
-- A read finds by lookup_key and is then refused unless every citation re-verifies against
-- the corpus NOW. The content key makes a corpus move visible without re-reading anything;
-- the re-verification is what actually decides.
--
-- ## Tenant scope: every row, no exceptions, in this version
--
-- PLAN_23 says "never across tenants for client documents", which would permit sharing a
-- purely statutory answer between tenants. This table does NOT permit it: tenant_id is in
-- the primary key and the policy is the same FORCE RLS as every other tenant table.
--
-- The reason is asymmetry of harm. Sharing buys a higher hit rate. Being wrong once about
-- whether an answer was derived from a client's contract shows one firm another firm's
-- document, which is the single worst thing this system could do. A shared cache for
-- answers provably free of client data is a later migration with its own proof -- the
-- pattern exists already in 009_source_documents, which is deliberately NOT rls-bound
-- because one SEBI circular is one public row. Until then the hit rate is lower, and that
-- is a stated price rather than a quiet one.
--
-- ## Nothing here is authoritative
--
-- Every row is DERIVED: it can be deleted at any time and the only consequence is that the
-- question is answered again. No decision may ever rest on this table's contents, which is
-- why it holds no status of its own and stores the payload verbatim.
--
-- STATUS: applied 2026-10-01 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-014 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 248 checks, 0 failures, then the database dropped. Both tables are proved the way the
-- other seventeen are -- A sees its own and none of B's; the policy dropped fails CLOSED;
-- RLS disabled LEAKS B's rows, which is what shows the check measures the protection;
-- restoring returns to isolation.

BEGIN;

CREATE TABLE IF NOT EXISTS answer_cache (
    tenant_id   uuid        NOT NULL REFERENCES tenants(tenant_id),
    lookup_key  text        NOT NULL CHECK (lookup_key ~ '^[0-9a-f]{64}$'),
    content_key text        NOT NULL CHECK (content_key ~ '^[0-9a-f]{64}$'),
    question    text        NOT NULL CHECK (length(btrim(question)) > 0),
    task        text        NOT NULL CHECK (length(btrim(task)) > 0),
    as_of       text        NOT NULL,
    sources     jsonb       NOT NULL DEFAULT '[]'::jsonb
                            CHECK (jsonb_typeof(sources) = 'array'),
    -- The citations, as stored at answer time. A row with an empty array is refused: an
    -- answer that cites nothing can never be shown to be still true, so caching it would
    -- create a row that `answer_cache.servable` must always reject -- a row whose only
    -- possible use is to be refused.
    citations   jsonb       NOT NULL
                            CHECK (jsonb_typeof(citations) = 'array'
                                   AND jsonb_array_length(citations) > 0),
    -- Whatever the answering verb returned, verbatim. Called `payload` and not
    -- `envelope` because it is the VERB'S result: the envelope is built from it
    -- afterwards, and a column named for the wrong layer is a column someone
    -- eventually fills with the wrong thing.
    payload     jsonb       NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    served      integer     NOT NULL DEFAULT 0 CHECK (served >= 0),

    PRIMARY KEY (tenant_id, lookup_key)
);

-- Hit-rate accounting, per tenant and per day. Counters and not a log: the question
-- "does this cache help" needs totals, and a row per lookup would be a second, larger
-- record of every question a lawyer has asked, which conversations already hold once.
CREATE TABLE IF NOT EXISTS answer_cache_stats (
    tenant_id uuid    NOT NULL REFERENCES tenants(tenant_id),
    day       date    NOT NULL,
    hits      integer NOT NULL DEFAULT 0 CHECK (hits   >= 0),
    misses    integer NOT NULL DEFAULT 0 CHECK (misses >= 0),
    -- Found, and refused because a cited provision had changed. Counted apart from a plain
    -- miss because it is not a cache fault: it is the corpus moving, and it is the number
    -- that says the re-verification gate is doing anything at all.
    stale     integer NOT NULL DEFAULT 0 CHECK (stale  >= 0),

    PRIMARY KEY (tenant_id, day)
);

CREATE INDEX IF NOT EXISTS answer_cache_tenant_idx
    ON answer_cache (tenant_id, created_at DESC);

ALTER TABLE answer_cache       ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_cache       FORCE  ROW LEVEL SECURITY;
ALTER TABLE answer_cache_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE answer_cache_stats FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON answer_cache;
CREATE POLICY tenant_isolation ON answer_cache USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON answer_cache_stats;
CREATE POLICY tenant_isolation ON answer_cache_stats USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE answer_cache IS
  'Derived rows only. Deleting the table costs nothing but re-answering; no decision may '
  'rest on it. An entry is served only when every citation re-verifies against the corpus '
  'as it stands at the moment of the read.';
COMMENT ON COLUMN answer_cache.content_key IS
  'lookup_key plus the sorted sha256 of every cited provision. A corpus move changes it, '
  'which is how a stale entry is visible without re-reading the corpus -- though the '
  're-verification, not this column, is what decides whether the answer is served.';
COMMENT ON COLUMN answer_cache_stats.stale IS
  'Found but refused because the law moved. NOT a cache fault, and counted apart from a '
  'miss so the hit rate cannot be flattered by hiding it.';

COMMIT;
