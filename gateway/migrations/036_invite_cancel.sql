-- 036_invite_cancel.sql — an admin can withdraw an invite that has not been used.
--
-- Cancelling MARKS the row; it never deletes it. Who invited whom, and who withdrew it,
-- stays on record. A cancelled invite cannot be accepted: accept_invite (gateway/store.py)
-- matches only `accepted_at IS NULL AND cancelled_at IS NULL AND expires_at > now()`, so
-- the invitee gets the same generic "not valid" answer as for a used or unknown token.
--
-- invites_live_per_email_idx is rebuilt to leave cancelled rows out, so cancelling an
-- invite frees the email for a fresh one. The index still cannot leave EXPIRED rows out
-- (a partial index may not call now()), so create_invite retires an expired invite for
-- the same email, in the same transaction, before inserting the new one.
--
-- Additive: two nullable columns and two CHECKs; no row is changed or removed. RLS is
-- unchanged -- `invites` is already ENABLE + FORCE with tenant_isolation, so another
-- firm's invite id matches no row in an UPDATE either.
--
-- 035 is claimed by the open spend-ledger PR (#159); this is numbered after it so the two
-- can merge in either order. migrate.py applies whatever is pending, in number order.

BEGIN;

ALTER TABLE invites ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
ALTER TABLE invites ADD COLUMN IF NOT EXISTS cancelled_by uuid REFERENCES actors(actor_id);

DO $$ BEGIN
    -- Cancelled means cancelled BY someone, as accepted means accepted by someone (018).
    ALTER TABLE invites ADD CONSTRAINT invites_cancelled_together CHECK (
        (cancelled_at IS NULL AND cancelled_by IS NULL) OR
        (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    -- An invite is used OR withdrawn, never both.
    ALTER TABLE invites ADD CONSTRAINT invites_not_accepted_and_cancelled CHECK (
        accepted_at IS NULL OR cancelled_at IS NULL);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DROP INDEX IF EXISTS invites_live_per_email_idx;
CREATE UNIQUE INDEX invites_live_per_email_idx
    ON invites (tenant_id, lower(email)) WHERE accepted_at IS NULL AND cancelled_at IS NULL;

COMMIT;
