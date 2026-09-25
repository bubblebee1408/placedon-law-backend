# Loop runbook — ten moves, in order

Created 2026-09-24. Pattern **sequential**, mode **safe**. One move at a time: a
subagent executes, this session reads the output and decides before the next
starts. **Bugs first, cleanup second, build third, ship last.** Nothing is
interleaved.

## Standing rules

1. **The gate is the contract.** `HARNESS_RESULT … status=GREEN`. A move that
   lowers it is reverted, not debugged forward. Baseline: **195 suites**.
2. **Never `SKIP_TESTS=1`.**
3. **A peer session shares this tree.** Stage explicit paths only, with a grep
   guard. Never touch `checker/provenance.py`, `checker/claim_verifier.py`,
   `checker/lawyer_summary.py`, `scripts/register_*.py`.
4. **Subagents work in their own worktree** and are integrated by named file
   (lesson S10 — the worktree tool branches from `origin/main`, not from here).
5. **Nothing is installed.**

## The PoSH question, decided before any deletion

The founder asked to "delete any PoSH Act which are not in need". Surveyed
2026-09-24. **Most PoSH references are not dead code, and deleting them would
remove a refusal or an explanation.** The distinction:

| Keep | Why |
|---|---|
| `docs/RETIRED_POSH.md` | The record of *why* the product was retired. Deleting it makes the decision unexplainable |
| `checker/scope.py` POSH entry | An **active, tested refusal** — `refusal_for("POSH")` returns "outside this product's scope". Remove it and a PoSH question gets silence, which reads as "no obligation found". That is the exact failure `scope.py` exists to prevent |
| `checker/ask_scope.py` POSH acronym | Routes a PoSH question to `out_of_scope` instead of a wrong answer |
| Docstring history in `assessment.py`, `matrix_view.py`, `text_search.py` | Recorded reasoning for why things are shaped as they are. Prose, not code |

| Delete — only if proven unreferenced | Status |
|---|---|
| `checker/templates/posh_policy.html` | No `grep` hit anywhere. **Candidate** |
| `applicability.py` `POSH_IC`, `jurisdiction.py` `POSH_RETURN` | Must prove no caller and no test first |
| `corpus/provisions/posh_act_2013.json`, `checker/retrieval.py` | Must prove unreferenced first |

**Rule: nothing is deleted without a proof of non-reference in the move's output.**

## The ten moves

### Phase A — find and fix what is already broken

| # | Move | Done when | Lane |
|---|---|---|---|
| **1** | **Bug sweep.** Run every suite individually; find dead code, unreferenced modules, broken imports, stale docs numbers, silent-failure shapes. Report only, change nothing | A ranked findings list with file:line and a reproduction for each | **DONE** — 7 findings; **0 unregistered suites** (193/193 registered); 195 GREEN in a fresh worktree |
| **2** | **Fix the small bugs** move 1 found, smallest first, one commit each | Each fix has the test that would have caught it; gate GREEN | **DONE** `282b896` — F1 (mine), F4, F6 fixed; F2/F3 left named (already FAILURE_MODES N13) |

### Phase B — cleanup

| # | Move | Done when | Lane |
|---|---|---|---|
| **3** | **Prove which PoSH artifacts are dead**, per the table above. Report, do not delete | A reference proof per candidate | **DONE** — done by this session rather than delegated; deletion is irreversible |
| **4** | **Delete only the proven-dead**, keeping every refusal and record | Gate GREEN; `refusal_for("POSH")` still answers | **DONE** `b12acee` — 5 files; `refusal_for("POSH")` still answers; gate unchanged at 195 |

### Phase C — build the real gap

| # | Move | Done when | Lane |
|---|---|---|---|
| **5** | **Operation store** — persist operations so `themis.get_operation` stops returning 501 | Create → store → fetch round-trips; git-ignored state | **DONE** `1eeea18` — 55/55; RT-08 and RT-09 both proven by crash injection |
| **6** | **Evidence submission** — move a requirement OPEN → SATISFIED with a named source; **a human closes BLOCKING ones, an agent never can** | Tested both ways: an agent's attempt on a blocking requirement is refused | **DONE** `1eeea18` — agent on BLOCKING refused with the store's own words |
| **7** | **Wire the MCP tools** to the store: `get_operation` real, `submit_evidence` added under policy | `get_operation` returns a stored operation; policy still refuses WRITE for agents | **DONE** `1eeea18` — `get_operation` real (404 absent / 500 corrupt); `submit_evidence` under a new narrow SUBMIT action |

### Phase D — verify and ship

| # | Move | Done when | Lane |
|---|---|---|---|
| **8** | **Red-team the store and the submission path** — can an agent close a blocking requirement, forge a source, or lose an operation? | Findings dispositioned | **DONE** — 5 findings, 2 FATAL. Both delegated agents stalled; run directly. `docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md` |
| **9** | **Full gate + `harness_regression.sh`** — prove the gate can still turn RED | 7/7 on the regression; suites GREEN | **DONE** — regression 7/7 across all three cases; the gate then went RED on a suite I had missed, which is the gate working |
| **10** | **Docs, push, PR** — update FEATURES/plan docs, push the branch, open a PR to `main` | `origin` matches local; PR open | me |

## Stop condition

Every move DONE or BLOCKED with evidence, gate GREEN, branch pushed. Or two
consecutive iterations with no progress for reasons outside this session.

**Not a stop condition:** "the plan is complete". H-C — one practising Company
Secretary reacting to the pack — has been open since 4 September and none of
these ten moves touches it.

## Log

- 24-09 — runbook written. Baseline 195 suites GREEN. PoSH survey done: most
  references are active refusals or recorded reasoning; deletion candidates must
  carry a non-reference proof.
- 25-09 — moves 1-4 landed and pushed. The sweep's most serious finding was in code
  this session wrote two days earlier: `_instrument_impact` rendered an unknown
  obligation id as an empty duty while the lawyer sentence still counted it. Third
  silent-default of that shape in the MCP layer this week -- a pattern about how this
  session writes, not bad luck. Fixed, with the drift-forcing test that proves it.
- 25-09 — PoSH: 5 files deleted, each with a non-reference proof. Kept every refusal:
  `scope.py`'s POSH entry is ACTIVE and tested, and removing it would turn an honest
  "outside this product's scope" into silence, which reads as "no obligation found".
- 25-09 — moves 5-7 landed (`1eeea18`), gate 195 -> 196 GREEN, pushed.
  **A rule had to be narrowed, and it is recorded rather than quietly changed.** The
  MCP gateway declared itself read-only on 23-09; executing an operation means
  recording an answer, so that rule and the Operation Model could not both stand.
  The rule protected the CORPUS and ATTESTATION -- an operation's work queue is
  neither. So `SUBMIT` was added as the narrowest opening: one tool, reaching the
  operation store and nothing else, with WRITE and ATTEST still refused outright for
  every actor, and the store refusing an agent on BLOCKING work *independently* of
  the policy. Two guards, neither relying on the other.
- 25-09 — **move 8 found the day before's work was wrong at the root, and the founder's
  merged plan said so independently.** `themis.submit_evidence` took `actor_kind` from
  its caller; sending `"human"` closed both BLOCKING requirements of a live operation --
  terminal human review included -- and reached `can_close: True`, while the handshake
  promised every client that only a human could (RT-10). The store is also tenant-blind
  (RT-14), so that write crossed tenants. PLAN_16-18 merged the same morning; PLAN_17 M6,
  written a day BEFORE the tool was built, already said: *"gateway route only (NOT an MCP
  tool: the MCP surface stays read-only)."*
  The narrowing of 24-09 is therefore reverted, not patched. The argument for it was
  sound and irrelevant: what mattered was never what SUBMIT could reach, but that **a
  permission is only as strong as the identity it is granted against**, and this
  surface's identities are claims it says itself it cannot verify. Reads survive that;
  writes do not. The submission path stays in `operation_store.py` (with RT-11 and RT-12
  fixed) for the authenticated gateway at M6.
  Third lying-doc defect in three days (RT-13: `tools.py` denied the existence of a tool
  it registered; `server.py` had two more stale lines the sweep caught). Pattern noted in
  the findings doc.
- 25-09 — two bugs found by this session's own tests, both mine: a default argument
  bound at definition time made the store un-redirectable (a test pointed at a temp
  dir; the tool kept reading the real one), and `initialize` was telling every MCP
  client "Every tool is read-only" after that stopped being true. A false claim
  travelling to an agent would have been believed.
