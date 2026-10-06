#!/usr/bin/env bash
# One-command initialisation. Idempotent — safe to re-run.
#
# Does NOT install torch, transformers or chromadb. The agent index is BM25F over 6,000 lines
# and runs in 0.05 ms; see scripts/index_codebase.py for the measurement and the condition
# under which that decision should be revisited.
set -euo pipefail
cd "$(dirname "$0")"

echo "placedon-law-backend setup"
echo

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit(f"Python 3.10+ required, found {sys.version.split()[0]}")
print(f"  python {sys.version.split()[0]}")
PY

# Install from requirements.txt, not a hand-kept list. The hardcoded list had already drifted:
# it omitted python-multipart (which IS pinned) and named three packages that are pinned nowhere,
# so a fresh environment could silently get versions nobody had tested.
if python3 scripts/check_deps.py >/dev/null 2>&1; then
  echo "  python deps present"
else
  echo "  installing from requirements.txt"
  python3 -m pip install --quiet -r requirements.txt
  [ -f requirements-dev.txt ] && python3 -m pip install --quiet -r requirements-dev.txt
fi

mkdir -p .claude/{today,memory,loops,commands}
[ -f .claude/today/TODAY.md ] || cat > .claude/today/TODAY.md <<'MD'
# TODAY

## Goal
(one sentence — run /start to set it)

Status lives in research/TASKS.md and the HARNESS_RESULT line, not here.
MD

# The web app is a separate repository (placedon-claude-legal-3300); there is no frontend/
# here. The old block below tried `cd frontend` and failed on every run.

echo
# Git merge drivers for the three files two branches always churn on. Registered in the
# LOCAL .git/config (never committed); .gitattributes selects them. Idempotent.
echo "  registering merge drivers (suite_floors / TASKS / REPO_MAP)"
git config merge.suitefloors.name "max floor per suite" || true
git config merge.suitefloors.driver "python3 scripts/merge_suite_floors.py %O %A %B" || true
git config merge.tasks-union.name "union of TASKS ledger rows" || true
git config merge.tasks-union.driver "python3 scripts/merge_tasks.py %O %A %B" || true
git config merge.repomap.name "regenerate docs/REPO_MAP.md" || true
git config merge.repomap.driver "python3 scripts/merge_repo_map.py %A" || true
echo

python3 scripts/index_codebase.py | head -3
echo
./scripts/run_tests.sh | tail -3

cat <<'MD'

Ready.

  python3 scripts/serve_api.py                    # /v1 engine on :8020
  python3 scripts/serve_matrix.py                 # compliance matrix on :8014
  PYTHONPATH=. python3 gateway/cli.py --help      # /v2 verbs as a CLI

  /start              open a session
  /build <feature>    full R-D-B-V-L loop
  /fix <bug>          reproduce, ratchet, fix, verify
  /research <topic>   research only, no code

  python3 scripts/search_memory.py "<question>"   ask the codebase first
  ./scripts/run_tests.sh                          every suite
MD
