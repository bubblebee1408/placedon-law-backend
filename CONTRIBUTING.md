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
4. Run `python3 scripts/repo_map.py` to regenerate [docs/REPO_MAP.md](docs/REPO_MAP.md) so the
   index names your module. This is no longer gate-enforced — the map is a generated index,
   regenerated on merge by a driver (see below) — but a current map is still courteous.

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

### The gate is deterministic: no keys, no paid calls, no network

The gate uses deterministic model stand-ins everywhere, so it gives the **same result on
every machine** — a laptop with keys in `.env`, a fresh clone with none, or CI. The stand-ins
replace only the model; retrieval, quote byte-matching, the critic and the envelope all run
for real. So a green gate never depended on a key and never made a paid call.

```bash
./scripts/run_tests.sh --live      # opt-in: the gateway conversation.send checks against the
                                   # REAL provider. NOT part of the gate — it touches no floors
                                   # and makes paid calls. Needs a model key in .env; with none
                                   # it prints BLOCKED and exits 0 (not a failure).
```

Run `--live` when you change the model path and want to confirm the live provider still yields
the statuses the stand-ins stand for (ANSWERED, PARTIAL, NEEDS_LAWYER). It is never required
for a green gate.

### A floor may be gated on a capability

`scripts/suite_floors.json` entries are usually a number. A suite whose check count depends on
an optional import (e.g. `sentence_transformers`, which is in no requirements file) uses a
gated floor instead:

```json
"checker/dense_index.py": {"floor": 8, "requires": "sentence_transformers",
                           "unavailable_floor": 1}
```

The full `floor` applies only when the import is present; otherwise the suite reports its
unavailability line and the smaller `unavailable_floor` is enforced — so the gate is honest on
a machine that lacks the optional package, without that package becoming a dependency.

### Proving a fresh clone is green

The gate must pass on a genuinely clean machine, not just a dev laptop that has stray caches,
globally-installed extras or a `.env`:

```bash
python3 -m venv /tmp/cleanenv
/tmp/cleanenv/bin/pip install -r requirements.txt -r requirements-dev.txt
# then, from a fresh clone, with an empty HOME and no .env:
env -i HOME=/tmp/emptyhome PATH=/tmp/cleanenv/bin:/usr/bin:/bin PYTHONPATH="$PWD" \
    bash scripts/run_tests.sh      # must be GREEN
```

A Docker `python:3.11` container with the same steps works too. A suite that passes on the
laptop and fails here is reading something the clone lacks — fix it (commit the file if its
licence allows, have `setup.sh` fetch it, or report BLOCKED with the reason), never lower a
floor to hide it.

## Three files resolve their own merge conflicts

Two branches both ratchet floors, append task rows and regenerate the repo map, so a merge
used to conflict on these three files every time — and each had exactly one correct
resolution. That resolution is now a git merge driver, selected by `.gitattributes`:

| File | Driver | Resolution |
|---|---|---|
| `scripts/suite_floors.json` | `scripts/merge_suite_floors.py` | the **max** floor per suite, keeping capability gates |
| `research/TASKS.md` | `scripts/merge_tasks.py` | a three-way merge, conflicts **unioned** by ledger-row id (ours wins a clash) |
| `docs/REPO_MAP.md` | `scripts/merge_repo_map.py` | both sides discarded, **regenerated** from the tree |

The drivers live in your **local** `.git/config` and `setup.sh` registers them — they are
never committed, so a clone that has not run `setup.sh` simply falls back to an ordinary
conflict (safe, just manual). Run `setup.sh` once after cloning. Each driver has a self-test
in the gate (`scripts/merge_*.py --test`).

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
