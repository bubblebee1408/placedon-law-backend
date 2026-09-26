# M11 — `checker/observation_store.py`: no index, because an index is the only thing that can be lost

Architect record, 2026-09-26, for move 11 of
`.claude/plans/loop-twenty-moves-2026-09-26.md` (PLAN_19 G1.2). Written before code, per
PLAN_19 §2.2 — the module adds a ring entry.

## 0. Doubt pass on PLAN_19 §3

§2 named four types that did not exist (see `M10_ONTOLOGY.md`). §3 is much better, but
not clean.

| §3 says | Reality | Checked |
|---|---|---|
| `append(obs, *, actor: Identity)` | **No `Identity` type exists.** Two prose mentions in `mca_strip.py` and `provenance.py`, no type | `grep -rn "^class Identity\|^Identity = "` |
| *"`event_log.py` already models `at` (valid time) and `known_at` (transaction time)"* | **TRUE.** `event_log.Event` carries both | enumerated its dataclass fields |
| *"reuses the four properties `operation_store.py` was red-teamed into… RT-11: a lost update is refused"* | **RT-11 cannot apply to rows here**, and §3 does not notice why. See §2 below — it is a stronger position than §3 claims, not a weaker one | read `operation_store.save` and RT-11 |
| — | **A second source shape already exists**: `event_log.Source` is `(instrument, as_at, sha256, url)`, unrelated to `provenance.SourceRecord` `(source_id, source_title, source_url, official, accessibility, retrieved_on, …)`. `ontology.SourceRef` chose `SourceRecord`. Pre-existing divergence, recorded, not fixed here | enumerated both |

## 1. `Identity` is `(actor: str, actor_kind: str)`, recorded as a CLAIM, gating nothing

Reuse `operation_store`'s existing pair — `HUMAN` / `AGENT` — rather than invent a type.

**And the store must grant nothing on the strength of it.** RT-10, three days ago: the
MCP submit tool took `actor_kind` from its caller, an agent sent `"human"`, and it closed
the terminal human-review requirement of a live operation. The lesson was written down as
*a permission is only as strong as the identity it is granted against*.

So here `actor` and `actor_kind` are **stored, never consulted**. `append` and `retract`
do the same thing whoever calls them; the pair exists so a reader can see who claimed
what. An append-only store does not need to gate on identity, because nothing it does is
destructive — which is the second reason the design below is chosen.

## 2. No index. RT-11 is then structurally inapplicable rather than handled

RT-11 in `operation_store`: `save()` writes a **whole-object snapshot**, so two callers
who each read the same operation and closed a different requirement produced a state file
holding only the second one's work. The fix was to refuse a stale copy.

An append-only log has no in-place row write, so no row can be lost that way. **But an
INDEX can.** A `{entity, prop} -> [offsets]` index is a mutable whole-file structure, and
rebuilding it after two concurrent appends is exactly RT-11 again, one layer down.

**Decision: no index for the beta.** `as_of` and `history` scan the JSONL. Consequences,
stated rather than discovered:

- **Cost.** O(n) per query. For beta n this is microseconds, and PLAN_19 §3 already says
  the store moves to the PLAN_18 Postgres `observations` table at M4, where the index is
  the database's problem and is transactional.
- **Benefit.** There is no derived structure that can disagree with the log. The log *is*
  the state. That is the strongest available form of "nothing is updated in place".
- **A test pins it:** the module must contain no code that writes any file other than the
  append log. Checked by an AST/grep scan, in the style of `release.py`'s SERVABLE-site
  scan, not by reading.

If a later measurement shows the scan is too slow, the honest fix is the Postgres move,
not a cache. A cache here re-introduces RT-11 for a speed nobody has yet measured a need
for.

## 3. `ObsId` is content-addressed

`sha256` of the canonical JSON of the row, first 16 hex. Not a counter.

- A counter needs a mutable "next id" — the same lost-update shape as an index.
- A content-addressed id is **verifiable**: a reader can recompute it and detect a row
  that was edited in place. A sequential id cannot tell you that.
- Collision on identical content is not a bug: the same observation appended twice IS the
  same observation. `append` returning the existing id is correct behaviour, and a test
  asserts it rather than leaving it to chance.

## 4. Retraction is a new row, and RETRACTED is already a provenance state

`retract(obs_id, reason, actor)` appends a row whose `evidence` is
`provenance.RETRACTED` — which already exists in `STATES`, verified. Nothing is deleted
and nothing is rewritten.

`as_of(known_at=T)` therefore **ignores any retraction appended after T**, which is the
whole point: it reproduces what we would have said on T, not what we believe now.

## 5. The three gate tests, written first

1. **Theorem 6 (replay).** Append, read `as_of(known_at=T1)`, retract, read
   `as_of(known_at=T1)` again → **byte-identical**. The retraction is invisible to a
   query about a moment before it.
2. **No-rewrite scan.** An AST walk proving no path opens the log in a truncating mode
   and no path calls `unlink`/`remove`/`rmtree` on it. A comment claiming append-only is
   not append-only.
3. **Crash injection (RT-08/RT-09).** Monkeypatch `os.replace` to raise at the instant
   the state file would move, and assert the log already holds the truth — the exact
   proof shape `operation_store._test()` uses, copied rather than re-derived.

## 6. Minimum content, not minimum presence

RT-12's family, four instances in two days: a guard that tests for PRESENCE is not a guard
that tests for CONTENT. `Observed.__post_init__` (move 10) already refuses `None`, a
non-`STATES` evidence word and an empty licence. This module adds:

- `retract` requires a `reason` with actual content, not merely non-empty. A retraction
  nobody can explain is a retraction nobody can audit — and `"."` closed a requirement
  three days ago for exactly this reason.
- `append` refuses an `Observed` whose `known_at` is in the future relative to the store's
  clock argument. A transaction time we have not reached cannot be a time we recorded
  something.

## 7. Ring and scope

Ring 1, registered in `rings.py`. It imports `ontology` (Ring 1) and `provenance`
(Ring 0) — sideways and downward, both permitted. No Ring 0 decider may import it.
Static imports only.

Not in scope: `event_log` reading `known_at` from this store (move 12), any rollup
(move 13), any tenant scoping (PLAN_18 M4).
