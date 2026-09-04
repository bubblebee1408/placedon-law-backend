# Next-move plan & autonomous loop runbook — 2026-09-04

Written so work continues turn-over-turn while the operator is away. This file IS
the loop's durable state: each iteration reads the queue, does the next AUTONOMOUS
task, commits+pushes, ticks the box here, and schedules the next iteration. It is
pushed to the remote, so it survives context loss and the local-checkout-vanish
that already happened once this session.

## The one rule the loop must never break

**Do not perform a human-gated step.** Two are outstanding and neither may be
faked, because faking either corrupts the guarantee the whole system exists to
make:
- `--attest` G.S.R. 700(E): certifies a *person* checked identity + verbatim
  clause. A script self-attesting defeats the two-human-checks design.
- Lawyer/CS confirmation of "correct span" and obligation correctness (H-001).

While these are outstanding the loop works AROUND them; it does not decide them.

## Current state snapshot (what is real and green)

- Deterministic engine: obligation register, 8 obligations + deciders, small-co
  classify, E3→E6 entailment gate, evidence pack, loopback serve, benchmark
  governance. Full suite green.
- Currency engine (`checker/currency.py`) + pack LAW-CURRENCY WATCH wiring.
- Model plan (`docs/MODEL_DEVELOPMENT_PLAN.md`), primary-source verified.
- **G.S.R. 700(E) downloaded, registered, PENDING_HUMAN_REVIEW** (sha256
  bb590caf…, committed). Small-company thresholds stay UNRESOLVED until the
  operator runs `--attest`.
- **Structural chunker (`checker/structural_chunk.py`)** — DONE this session.

## The autonomous queue (RAG/retrieval layer, model plan §3.3/§6)

Ordered. Each task: deterministic, self-tested ([PASS]/[FAIL], N/N), zero new
deps, one commit, full runner green before push. Tick when merged.

- [x] **T1 — Structural chunker.** `chunk_section()` splits a section on its own
  units (sub-section/proviso/roman sub-clause) with paths + spans + hashes.
  *Done, 21/21, pushed.*

- [x] **T2 — Structural corpus index.** `checker/structural_index.py`: build a
  path→chunk index across all ~529 sections (lazy, cached), plus
  `chunk_by_path("2(85)(i)")` and `chunks_for_section("96")`. Acceptance: every
  obligation's governing provision (s.96, s.173, s.149(1), s.149(3), s.137, s.92,
  s.135, s.2(85)) resolves to at least its sub-section chunk; s.2(85) resolves to
  both limbs. Guard: must not choke on a section whose HTML is malformed —
  degrade to a chapeau chunk, never raise.

- [x] **T3 — Retrieval returns structural chunks.** Add a function (do NOT break
  existing `retrieve()` tests) that, given a section (and optional path), returns
  the ranked structural chunks, each carrying its citation path + hash. Keep the
  existing admission/withheld-rules discipline. Acceptance: a query naming a
  section returns its chunks with paths; a withheld rule stays withheld.

- [ ] **T4 — Chunk → E-gate candidate span.** `checker/ground_span.py`: given a
  model-proposed claim + a section, deterministically pick the best-matching
  structural chunk as the candidate witness span, then hand it to the existing
  E3→E6 cascade. This is the "model proposes, cascade disposes" wiring from the
  plan (§3.5). Acceptance: a claim about the small-company capital limit selects
  chunk 2(85)(i), and a claim unsupported by any chunk yields NOT_ESTABLISHED.
  Match deterministically (path mention, then term overlap); NO model in the
  selection path.

- [ ] **T5 — Retrieval eval harness (scaffold).** `checker/retrieval_eval.py`: a
  frozen set of (question → expected chunk path) cases with a scorer
  (precision@1 / recall). Seed ONLY the entries derivable without legal judgement
  (e.g. "small company paid-up capital limit" → 2(85)(i); "AGM timing first year"
  → 96(1)/proviso[1]). Mark every semantically-judged entry `NEEDS_LAWYER` and
  EXCLUDE it from the score so no false green. Acceptance: harness runs, scores
  the seed set, and lists the NEEDS_LAWYER gaps as the H-001 ask.

- [ ] **T6 — Wire structural citations into the pack.** When a pack row cites a
  provision, attach the structural chunk path + hash behind it (from T2), so the
  evidence pack cites "s.2(85)(i)" not just "s.2(85)". Acceptance: at least the
  small-company row shows a sub-clause-level citation; no bare statutory text
  (s.52(1)(q)(ii)); pack suite stays green.

## Human-gated (do NOT do in the loop — leave for the operator)

- [ ] **H-A — Attest G.S.R. 700(E).** `python3 scripts/register_gsr700e.py
  --attest <id>` after eyeballing `corpus/sources/gsr700e_2022.pdf`. Then run the
  suite; commit the attested record; currency flips 2(85) → CURRENT. Prep the
  loop can do: nothing further — it is genuinely one operator command.
- [ ] **H-B — Lawyer confirms T5 NEEDS_LAWYER spans** and the obligation rows.
- [ ] **H-C — CS review via the validation kit (H-001).**

## Loop protocol (how each iteration runs)

1. Read this file; find the first unchecked `[ ]` task in the AUTONOMOUS queue.
2. If none remain (all done or only human-gated left): STOP the loop, write a
   final summary to this file, do not reschedule.
3. Otherwise: build it TDD-style — module with self-tests, run it, register in
   `scripts/run_tests.sh`, run the FULL suite, and only push if green.
4. One logical change per commit; push to `engine/entailment`; tick the box here
   and commit this file too.
5. Schedule the next iteration. On any failure that cannot be fixed in-iteration,
   write the blocker under the task, STOP, and leave it for the operator.

## Definition of "done for today"

The autonomous queue (T2–T6) merged and green, OR a blocker recorded and the loop
stopped honestly. The human-gated items (H-A/B/C) are the operator's and are not
part of today's autonomous completion — the highest-value one, H-A, is a single
command that unblocks small-company classification the moment the operator is back.
