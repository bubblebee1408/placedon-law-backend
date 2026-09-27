# 06: Loop prompts: how Claude Code builds PLAN_19, one move at a time

This is the operating manual for building phases G0–G6 with `/loop` and the subagents in
`.claude/agents/`. Every prompt below can be pasted as is.

## 0. A prerequisite found while writing this

The repo's own `/loop` command (`.claude/commands/loop.md`) was written for the PoSH product.
Its pre-flight step read `corpus/provisions/posh_act_2013.json` and called `scripts/verify.py`.
**Neither file has ever existed in this repository.** `git log --all` finds no commit touching
either path, so the command was carried over from another codebase and never run here. A
`/loop` run would have failed on its first command.

The pre-flight is fixed in its own commit alongside this plan, and now calls
`scripts/verify_green.sh` and the gold set. `.claude/commands/start.md` has the same stale check
and a PoSH-era buyer framing. It is **not** fixed here, because it needs a rewrite, not a line
edit. It is recorded as open.

## 1. The master loop prompt

Paste this once to start. It runs one **move** per iteration and stops on any stop condition.

```
/loop PLAN_19. Read docs/plan19/00_INDEX.md and 05_ROADMAP.md, then research/TASKS.md.
Pick the FIRST step in 05_ROADMAP.md whose entry gate is met and whose exit is not.
Do exactly that one step, using its prompt in docs/plan19/06_LOOP_PROMPTS.md §3.
Protocol per move (06 §2) is mandatory. Stop and report on any stop condition (06 §4).
Never skip the gate. Never use SKIP_TESTS. Stage explicit paths only.
```

## 2. The per-move protocol (every step, no exceptions)

1. **Doubt pass, before code.**
   - Restate the step's "done when" as a test you will write first.
   - List the files you will touch and read each in full.
   - If the step rests on a claim tagged [S], [I] or [OPEN] in docs/plan19, say so and check it,
     or stop.
2. **Architect, if the step changes a schema, adds a dependency or adds a ring.** Spawn
   `architect`. Its decision is written down before `developer` starts.
3. **Build.** Spawn `developer` with the step prompt. It writes the test first and watches it
   fail. Tests live in the module's `_test()` and run under `scripts/run_tests.sh`.
4. **Verify, independently.**
   - Spawn `qa-reviewer` on the diff.
   - Spawn `trust-boundary-reviewer` if anything user-facing changed.
   - Spawn `legal-verifier` if any legal statement, evidence order or served state changed.
   - Any veto stops the move.
5. **The gate.** Run `bash scripts/verify_green.sh`. Exit code 0 is the only green. Any other
   code is red, including 3 (no result line) and 4 (a contradiction).
6. **Commit.** One logical change per commit. The message says *why*. Stage named paths only,
   because a peer session may share the tree. Never sweep, and never remove another session's
   `.git/index.lock`.
7. **Record.**
   - Update the step's row in `research/TASKS.md`, with the commit hash.
   - If it cost something, add a lesson to `.claude/memory/LESSONS.md`.
   - A number goes in only if it was measured this move, and with its n.

## 3. Step prompts

Each prompt names its subagent, its inputs and its definition of done. `{…}` marks values the
loop fills in from the ledger.

### G0.1: anchor `acquisition_for` · developer

```
Fix checker/currency.py acquisition_for (line ~269). Today it matches by unanchored substring:
"Companies Act 2013" and "G.S.R." alone return read=True; registered-but-unread instruments
(KMP, PAS, SEBI) return None, conflating unknown with not-attested. Write failing tests first
for those four inputs. Then: match only whole registered instrument ids (the same normaliser
affected_by uses, anchored); return a distinct PENDING Acquisition for registered-but-unread;
return None only for an id not registered at all. Check every caller (grep acquisition_for) —
operations.py R0 and mcp/tools.py branch on it — and add a test at each caller for PENDING.
Done when verify_green exits 0 and the four inputs behave as stated.
```

### G0.2: freeze the held-out split · benchmark-engineer

```
Split eval/goldset/questions.jsonl into dev and test, stratified by provenance and by
held/unheld body, using a seeded shuffle whose seed is committed. Write eval/goldset/split.json
with the ids of each side and the sha256 of the test ids. Change run.py so --split test
records its run in eval/goldset/test_runs.jsonl and refuses a second test run against the same
code hash unless --new-hash is given with a written reason. Never look at test-split outcomes
while building G0.3/G0.4. Done when the split is committed BEFORE any G0.3/G0.4 commit.
```

### G0.3: scope gate from practitioner phrasing · legal-source-researcher, then developer

```
Researcher: for each of the 7 unheld bodies in checker/scope.py, write a lexicon of terms that
signal the body WITHOUT naming it — defined terms, signature concepts, regulator forms — each
term with the provision of that Act it comes from (e.g. "open offer" -> SAST Regulations
reg.3/4). Primary sources only; if a provision cannot be confirmed, the term goes in marked
UNVERIFIED and is NOT used by the gate. Output: checker/scope_lexicon.json (new) + a sourcing
note in docs/research/.
Developer: ask_scope.py uses verified lexicon terms as a third signal after title and
regulator. A lexicon hit on an unheld body refuses with that body named. Ambiguous hits (two
bodies) refuse naming both. Done: dev split 7/7 practitioner phrasings refused; no held-law
dev question newly refused (report any as a regression, do not tune it away); test split run
ONCE, reported as count + Wilson interval.
```

### G0.4: abbreviation lexicon · corpus-engineer, then developer

```
Build checker/abbrev.json from the Companies Act's own text: s.2 definitions and defined
abbreviations (KMP -> "key managerial personnel", s.2(51)), each with its provision. No entry
without a provision. Developer: text_search expands a query term only through this lexicon,
and the expansion is visible in the evidence pack (never silent). Measure on dev; then one
test-split run; compare to the incumbent with McNemar (docs/plan19/04 §8). If n is too small
to decide at alpha 0.05, write "undecided at n=…", not "improved".
Do NOT touch MIN_COVER or SCORE_FLOOR — the 25 Sep relaxation regressed the nonsense-query
tests and was reverted.
```

### G0.5: declare the evidence order · legal-verifier (decision only)

```
Decide the total order over provenance.STATES for evidence strength (proposal in
docs/plan19/04 §1). The question that needs a legal answer: is UNFETCHED_CORROBORATION
(an inaccessible source reported to agree) stronger than INFERRED (our own derivation)?
Write the reasoning to docs/research/EVIDENCE_ORDER_<date>.md. Then developer adds
provenance.EVIDENCE_ORDER as a lattice.Lattice with a test that every STATES member appears
exactly once.
```

### G1.1–G1.2: ontology and observation store · architect → developer

```
Architect: confirm the rings for checker/ontology.py and checker/observation_store.py (both
Ring 1) and record it. Developer: implement docs/plan19/03 §2 and §3 exactly. Reuse
operation_store's log-first, atomic-write, lost-update and min-source-shape patterns — read
docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md first. Gate tests: (a) a dataclass-field
scan proves Individual has no name/DIN/PAN field; (b) Theorem 6 replay — append, retract,
then as_of(known_at=before-retraction) is byte-identical to the earlier answer; (c) there is
no code path that rewrites or deletes a row (grep test, like release.py's SERVABLE-site scan).
```

### G2.1–G2.3: derivation algebra · developer, then qa-reviewer

```
Implement checker/derivation.py per docs/plan19/03 §4. Property tests with a seeded RNG, 500
cases each: semiring axioms over provenance.EVIDENCE_ORDER (Theorem 1); minimal-witness
evaluation == full-DNF evaluation (Lemma 2); monotonicity (Corollary 3). Same-value guard
raises on conflicting values. Then the differential test: for every obligation the engine
serves today, the verdict and witness via derivation equal the existing lattice.worst_of
result. ANY diff stops the phase — report it, do not "fix" the old path to match.
```

### G3.1: watch engine · architect → developer

```
Implement checker/watch.py per docs/plan19/03 §5. Rules 1–4 there are tests. The
incremental-vs-full check replays every event_log event in date order and asserts equal
alert sets. An alert on an instrument whose acquisition is PENDING must carry
BASIS_UNACQUIRED and output_class SIGNAL. A subscription to a company or provision under an
unheld body returns the scope refusal, never an empty list.
```

### G3.2 / G3.3: feeds · corpus-engineer

```
Add the source through checker/feeds/common/fetch.py only (robots, TLS, RT-04 truncation).
Record a fixture; tests run on the fixture; live fetch only behind an explicit flag. For
data.gov.in: API key + ZIP only, never HTML (robots.txt Disallow: /); GODL attribution string
rendered wherever a value from it appears; the key is an env var, never in the repo. Before
the first live call, quote the source's current terms into docs/research/ with the fetch date.
If the terms page is unreachable, STOP: a 403 or egress block is not permission.
```

### G4.1: verb table, no behaviour change · developer

```
Create checker/verbs.py wrapping today's routes (checker/api.py) and MCP tools
(checker/mcp/tools.py). Record fixtures of every route's and tool's current output first.
Generate MCP tools from VERBS; the existing scripts/themis_mcp.py tests must pass unchanged.
Parity test: verb sets equal across mcp_tools(), cli_parser(), http_routes(); payloads
byte-identical to the fixtures. No WRITE or ATTEST verb is exported to MCP (RT-10).
```

### G5 and G6

These are written when G4 exits. They depend on counsel (the CC-BY question) and on the founder
(the OpenSanctions budget), and a prompt written now would encode guesses about both.

## 4. Stop conditions: the loop halts and reports

- `verify_green.sh` is not exit 0 after one fix attempt on your own change. If the red suite
  belongs to a peer session, wait and do not touch it.
- A reviewer subagent vetoes.
- A step needs a source that is blocked, egress-denied or unread. Record it [BLOCKED] and move to
  the next unblocked step.
- A step would add a dependency, change a legal claim or migrate a schema without an architect or
  legal-verifier record.
- Any temptation to state a rate below n = 30, or to score a test split twice.
- Three consecutive moves with no commit. Report why rather than continuing.

## 5. The report each iteration ends with

`CLAUDE.md`'s code-task format:

- Files changed
- Tests added or updated
- Commands run
- Results
- Known limitations
- Commit hash

Plus one line: **the next step, and whether its entry gate is met.**
