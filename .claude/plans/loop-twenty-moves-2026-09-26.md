# Loop runbook — the next twenty moves

Written 2026-09-26. Extends PLAN_19's G0–G7 roadmap; does not replace it. Where
PLAN_19 decides something this file cites it. Where measurement has overruled
PLAN_19, that is stated with the evidence.

**Pattern `sequential`, mode `safe`. ONE subagent at a time, never two in parallel** —
five of six subagents launched on 25-09 died on the shared usage limit, and two
parallel agents on 26-09 both died at once. Each subagent spends the same budget the
main session needs.

## Standing rules (unchanged, and every one has been paid for)

1. **The gate is the contract.** `bash scripts/verify_green.sh`, exit 0 only.
   Baseline **200 suites**. A move that lowers it is reverted, not debugged forward.
2. **Never `SKIP_TESTS=1`.** It announces itself loudly and leaves the tree unverified.
3. **A peer session shares this tree.** Stage explicit paths. Never `git add -A`.
   Never delete another session's `.git/index.lock` — wait it out.
   Do not touch `checker/provenance.py`, `checker/claim_verifier.py`,
   `checker/lawyer_summary.py`, `scripts/register_*.py`.
4. **Nothing is installed.** No new runtime dependency without a written reason.
5. **No rate below n = 30.** Print the count and the Wilson interval. The gold set
   enforces this in code (`eval/goldset/__init__.py:MIN_N_FOR_A_RATE`).
6. **Never score the test split twice** against the same code hash. `run.py` refuses.
7. **A doubt pass before code** (PLAN_19 §2.1): restate "done when" as the failing
   test, list the files, read them in full.
8. **An architect record before any schema, ring or dependency change** (§2.2).

## What the last two days actually established

These are the reasons the order below is what it is, not commentary.

| Finding | Where | Consequence for this plan |
|---|---|---|
| **One response for four situations.** Law not held, law held but not retrieved, not a legal question, and wrong jurisdiction all return byte-identical `state: partial, confirmed: [], not_confirmed: [pack_missing]` | `docs/research/EMPTY_PACK_2026_09_25.md` | **M1 is refusal codes.** Nothing downstream can be measured until the envelope can tell these apart |
| **The gold set cannot judge retrieval.** A fix that made the engine answer *"how long should I boil eggs"* with `s.123, s.174, s.178` scored **identically** to the clean engine | same doc, §"the experiment that inverted the plan" | G0.4 (abbreviations) is **blocked on M1**, not on more data |
| **The cover gate discards correctly-ranked hits.** `s.177` is top hit at `score=0.819`, cut by `cover=0.377` | `docs/research/RETRIEVAL_DEFECT_2026_09_25.md` | Do NOT touch `MIN_COVER`/`SCORE_FLOOR`. The 25-09 relaxation regressed the nonsense tests |
| **The scope gate is a keyword matcher.** Named statute 7/7 refused; practitioner phrasing 2/7 | `docs/research/GOLDSET_FIRST_RUN_2026_09_25.md` | G0.3's lexicon, after M1 |
| **A permission is only as strong as the identity it is granted against** | `docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md` | No WRITE verb over MCP, ever, before M9 |
| **Human labels: 0 of 59** | `eval/goldset/` | No move below produces an accuracy claim. Only H-C can |

## The twenty moves

### Phase A — make failure legible (nothing else can be measured first)

| # | Move | Done when | Who |
|---|---|---|---|
| **1** | **Refusal codes on `placedon.ask/0`.** A typed `refusal` field naming which of the four situations occurred. `ask_scope` already returns `body=None`, `retrieve` returns `ROUTE_ABSTAIN`, `search()` returns `[]` — three distinguishable states collapsing into one output. Codes from PLAN_18 §2.4.1 | The four cases return four different codes; `web/assistant/contract.md` fixtures still pass; a transport error is still NOT a refusal | architect → me |
| **2** | **Gold set reads the refusal code.** `run.py` stops inferring REFUSED from `state`; it reads the code | The boil-eggs regression from 25-09 is now CAUGHT by the gold set. Re-apply the reverted retrieval fix and prove the gold set rejects it | me |
| **3** | **G0.3 scope lexicon.** Per-body signal terms from each Act's own text, each citing its provision. UNVERIFIED terms are recorded and NOT used | Dev split: 7/7 practitioner phrasings refuse. No held-law question newly refused. Test split run ONCE | subagent → me |
| **4** | **G0.4 abbreviation lexicon** from s.2 definitions, each entry citing its provision. Expansion **visible** in the pack, never silent. Do NOT touch `MIN_COVER`/`SCORE_FLOOR` | McNemar vs incumbent on the test split. If n too small: **"undecided at n=…"**, never "improved" | subagent → me |
| **5** | **G0.5 evidence order** — is `UNFETCHED_CORROBORATION` stronger than `INFERRED`? A legal question, decided and written down, then `provenance.EVIDENCE_ORDER` as a `lattice.Lattice` | Every `STATES` member appears exactly once; the reasoning is in `docs/` | legal reasoning → me |

### Phase B — trust what already exists

| # | Move | Done when | Who |
|---|---|---|---|
| **6** | **CI on.** Blocked: the token lacks `workflow`. Web-UI route documented | A PR runs the suite on a clean runner | **FOUNDER** |
| **7** | **The clean-clone measurement** (PLAN_17 M1.1). Five suites are expected to fail off this laptop — `pypdf`, a `chmod 000` test that root can read, a missing s96 witness, `review.py --test` | Each root cause named. **No assertion weakened.** A missing witness is a SKIP with a reason, never a pass | me |
| **8** | **`.nic.in` is alive again.** `provenance.py` still excludes it "on purpose: it is dead" — CLAUDE.md records the host now serves real PDFs. The permitted-host list refuses a host that works | A fetch asserts `Content-Type` **and** `%PDF` magic bytes, never status alone | peer session owns `provenance.py` — coordinate |
| **9** | **Red-team the registry** built in move 0 (G0.1), RT-08…RT-14 style | Findings logged; each fixed with a test or recorded as accepted | subagent → me |

### Phase C — the ontology and the algebra (PLAN_19 G1, G2)

| # | Move | Done when | Who |
|---|---|---|---|
| **10** | `checker/ontology.py` — PLAN_19 03 §2. `LINK_TYPES` from `entity_graph.Rel` | A dataclass-field scan proves no `Individual` carries a name/DIN/PAN field | architect → subagent |
| **11** | `checker/observation_store.py` — append, `as_of`, history, retract. Log first, atomic write. **Read the operation-store red team first** | Theorem 6 replay: append, retract, query at the old `known_at` → byte-identical. A grep test proves no path rewrites or deletes a row | subagent → me |
| **12** | `event_log` reads `known_at` from the store | The docstring's stated limitation is removed, **and only then** | me |
| **13** | `checker/derivation.py` — PLAN_19 03 §4 | Property tests, seeded RNG, 500 cases: semiring axioms, minimal-witness == full-DNF, monotonicity. Same-value guard raises | subagent → me |
| **14** | **The differential test.** Every obligation served today gives an identical verdict and witness through `derivation` | **Zero diffs, or the phase stops.** Do not "fix" the old path to match | me |
| **15** | `scripts/revocation_report.py` — retract a fact, list the conclusions affected | Demonstrated on G.S.R. 880(E) against a copy of the store | me |

### Phase D — one engine, three surfaces (PLAN_19 G4 = PLAN_17 M3 + M9)

| # | Move | Done when | Who |
|---|---|---|---|
| **16** | **Record fixtures of every route and tool FIRST**, before `verbs.py` exists | Byte-exact fixtures committed | me |
| **17** | `checker/verbs.py` wrapping today's 8 routes and 13 tools. **No behaviour change** | Parity: verb sets equal across surfaces; payloads byte-identical to move 16's fixtures. **No WRITE or ATTEST verb reaches MCP** (RT-10) | subagent → me |
| **18** | MCP tools generated from `verbs` | `scripts/themis_mcp.py` tests pass **unchanged** | me |
| **19** | CLI `scripts/themis` generated | `themis company events <cin> --as-of …` equals the HTTP payload byte for byte | subagent → me |

### Phase E — the only move that changes what may be claimed

| # | Move | Done when | Who |
|---|---|---|---|
| **20** | **H-C: one practising Company Secretary labels answers.** Open since 4 September — 22 days | ≥ 1 label. At 59, PLAN_16 C1's first calibration becomes possible | **FOUNDER** |

## After each move

Report in CLAUDE.md's code-task format: Files changed · Tests added · Commands run ·
Results · Known limitations · Commit hash. Plus one line: the next move, and whether
its entry gate is met.

## Stop conditions (PLAN_19 §4)

- `verify_green.sh` not exit 0 after ONE fix attempt on my own change.
- A red suite belonging to a peer session → **wait, do not touch it**.
- A reviewer veto.
- A blocked or egress-denied source → record `[BLOCKED]`, move to the next unblocked step.
- A schema, ring or dependency change with no architect record.
- Any temptation to state a rate below n = 30, or to score a test split twice.
- Three consecutive moves with no commit → report why rather than continuing.

## Not a stop condition

"The plan is complete." Moves 6 and 20 are the two that matter most and neither is
mine. Nineteen of these twenty moves can be done without a single lawyer seeing the
product, which is the failure mode this repository documents about itself.
