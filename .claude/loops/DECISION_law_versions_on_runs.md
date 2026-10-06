# Decision: NO migration. The column exists, and so does the identity.

**Date** 2026-10-05 · **Move** 6 (T1) · **Branch** `claude/overnight-b`

## What I was about to do, and why it was wrong

I had written `023_run_law_versions.sql` adding `corpus_hash text` and `law_basis text` to
`runs`, with CHECKs, a partial index and an architect record arguing for two named columns
over JSONB.

All of it was unnecessary. **`runs.law_versions jsonb` has existed since
`008_decision_evidence.sql`**, both store backends read and write it, and `review_document`
populates it today. I found this by reading `write_run` before editing it, which is the only
reason this file says "no migration" instead of shipping a duplicate column.

008 also states the rule I was about to break:

> {repo-relative path: git blob id} of the held text a run READ. … The same identity
> `public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer cache) compare one
> thing.

My `checker/law_versions.corpus_hash` was a **second** hash format for the same purpose —
sha256 over (path, sha256-of-bytes). Two identities for "which law was this" is precisely the
thing 008 spent a paragraph preventing, and the failure mode is quiet: O9 caches on one, a
dispute is argued on the other, and they never disagree until the day they do.

## The decision

**No new column.** Three changes instead:

1. `checker/law_versions.py` computes the **git blob id** per record — the same formula
   `law_versions_of` uses — and `corpus_hash` becomes a hash **of those blob ids**, not an
   independent digest of the bytes. One identity underneath, so the whole-corpus marker and
   the per-record map cannot disagree by construction.
2. `gateway/verbs.law_versions_of` **delegates** to the checker module. Ring 0 may not import
   Ring 2, and this direction is the legal one; it also deletes a second copy of the blob
   formula.
3. The `ask` path records `law_versions` on its run row for the records it actually read —
   which is what move 6 asked for, and what the existing column was always for.

`corpus_hash` stays in the envelope. It answers a different question from the per-record map
("which edition of the corpus", not "which records were read"), it is comparable by eye, and
it is now derived from the same bytes-identity rather than competing with it.

## Reversal condition

If `corpus_hash` is ever found to differ between the envelope and a run's `law_versions` for
the same run, there are two code paths computing one fact and the fix is one path — not a
reconciliation step. The check that would catch it belongs in the gate, and is the reason
`corpus_hash` is derived from `blob_ids()` rather than computed alongside it.

If a run ever needs to record more than one BODY of law — where the 13-body scope is heading —
the map's keys already carry the path, so `corpus/llp_act_2008/...` needs no schema change.
That is the second reason not to have added named columns.
