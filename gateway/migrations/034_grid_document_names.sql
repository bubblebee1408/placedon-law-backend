-- 034_grid_document_names.sql — the file name of each document in a review table.
--
-- A grid addresses documents by content hash (011), so until now the only place a file's
-- NAME lived was the browser that ticked it: reopening a table anywhere else showed
-- "File 1", "File 2". The name is copied here at review_table.create, from the vault
-- document (or the upload) the hash belongs to, so it survives a renamed or deleted vault
-- record as well. `{sha256: name}`; tables made before this migration read '{}' and the
-- page falls back as it did. Additive: no row or column is removed. RLS is unchanged --
-- the column lives on review_grids, already ENABLE + FORCE with tenant_isolation.

BEGIN;

ALTER TABLE review_grids
    ADD COLUMN IF NOT EXISTS document_names jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $$ BEGIN
    ALTER TABLE review_grids ADD CONSTRAINT review_grids_document_names_object
        CHECK (jsonb_typeof(document_names) = 'object');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMIT;
