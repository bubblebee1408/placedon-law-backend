# Contributing

How to make a change that the gate, and a reviewer, will accept. The rules are in
[CLAUDE.md](CLAUDE.md), and they bind people as well as coding agents. This file is the
working procedure that follows from them.

## Before you write code

1. **Inspect, then propose.** List the files your change touches before editing any of them.
   [docs/REPO_MAP.md](docs/REPO_MAP.md) gives one line per module, and
   [docs/START_HERE.md §5](docs/START_HERE.md) gives "where each kind of change belongs".
2. **Read the governing plan.** For models, retrieval, OCR, API or MCP work, read
   [PLAN_22](docs/plans/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md). For `agents/` or
   `gateway/`, read [PLAN_23](docs/plans/PLAN_23_ORCHESTRATION.md).
3. **Check that it is not already decided.** Each decision in PLAN_22 has a reversal
   condition, and [docs/evidence/RETRACTIONS.md](docs/evidence/RETRACTIONS.md) lists what was
   tried and withdrawn. Re-building something already decided against costs more than building
   nothing.
4. **Check the task ledger.** [research/TASKS.md](research/TASKS.md) is the single source of
   truth for what is open and who it is blocked on.

## Making the change

- **One logical change per commit.** No production code without a test.
- **No new dependency without a stated reason** in the commit message. The decision path is
  standard-library Python on purpose.
- **Respect the rings** (`checker/rings.py`). Ring 0 (legal core) may never import Ring 2
  (feeds, gateway, sources) or Ring 3 (agents, forecast). An AST walk in the gate enforces this.
- **Gateway changes:** add a verb in `gateway/verbs.py`. One entry generates REST, MCP and
  the CLI, and a parity test holds the three together. Write verbs stay off MCP.
- **Database changes:** add `gateway/migrations/NNN_*.sql`. Every tenant table gets FORCE
  row-level security. Run `scripts/rls_integration.py --run` against a real Postgres.
- **Legal content:** never invent a rule, a threshold, a section or a date. If evidence is
  incomplete, write `OPEN` or `UNVERIFIED`. Every finding carries source, date, rule ID,
  reasoning and confidence.
- **Untrusted text** (uploaded or retrieved) is data, never instructions. See the two-part
  rule on `prompt_safety.UNTRUSTED_CLAUSE` and `wrap_untrusted()` in CLAUDE.md.

## Tests: the self-test convention

There is no pytest. A testable module looks like this:

```python
def _test() -> None:
    passed = failed = 0
    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        ...  # print [PASS]/[FAIL] label, count it
    check(..., "what this proves")
    print(f"{passed}/{passed + failed} passed")

if __name__ == "__main__":
    _test()          # or: if "--test" in sys.argv
```

To add a new suite:

1. Give the module a `_test()` that prints `N/N passed`.
2. Add its path to the `suites=(...)` list in `scripts/run_tests.sh`.
3. If it needs a minimum check count, add a floor to `scripts/suite_floors.json`. The harness
   fails a suite that prints fewer checks than its floor, so a test cannot quietly shrink.
4. Run `python3 scripts/repo_map.py` to regenerate [docs/REPO_MAP.md](docs/REPO_MAP.md). The
   gate fails when the map is stale.

## Before you push

```bash
./scripts/run_tests.sh             # must end: HARNESS_RESULT suites=N failed=0 status=GREEN
python3 scripts/check_doc_refs.py  # every path a present-tense doc cites must exist
python3 scripts/repo_map.py        # if you added, removed or renamed a module
```

- Run **one gate at a time**, because a concurrent run fails on a fixed port.
- `status=BLOCKED` means dependencies are missing and nothing ran. Install them; do not reach
  for `SKIP_TESTS=1`.
- Compare the result with `main`'s. A failure that is red on `main` too is not yours, but say
  so in the PR.

## Documents

Documents live under [docs/](docs/README.md), filed by kind. Before adding or editing one,
know which **tense** it speaks in, because `scripts/check_doc_refs.py` treats them differently:

| Tense | Where | Rule |
|---|---|---|
| **Present**: what IS | `README.md`, `CLAUDE.md`, `docs/START_HERE.md`, `docs/architecture/`, `docs/guides/`, `docs/policy/`, `.claude/` | Every path cited must exist. Fix the doc when the code moves. |
| **Future**: what to build | `docs/plans/PLAN_*`, `docs/plans/plan19/` | May cite files that do not exist yet. That is the plan doing its job. |
| **Past**: what happened | `docs/reports/`, `docs/research/`, any file with a date in its name, the ledgers in `docs/evidence/` | **Never rewrite history.** A retraction, a ledger entry or a dated report records what was true on its date. Add a new dated entry; do not edit the old one. |

- **Superseding a document:** add one line at the top, `> **SUPERSEDED** <date> by <file>.
  Kept as history.`, and leave the body alone. Deleting a decision record is how a team
  re-litigates settled questions.
- **Numbers belong in one place.** Counts such as suites, sections and coverage go stale in
  prose. Cite the command that measures them (`HARNESS_RESULT`, `_manifest.json`'s `count`)
  instead of copying the figure.
- **A 404 is evidence of nothing.** "Could not verify" is not "does not exist". See PLAN_10 §0.

## Pull requests

- Branch from `main`, and open the PR as a draft until the gate is green.
- In the description, give: files changed, tests added or updated, commands run, results
  (the `HARNESS_RESULT` line), known limitations.
- Never commit secrets, `.env*` files, private minutes or confidential company documents.
  Permitted sources are listed in CLAUDE.md.
