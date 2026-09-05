#!/usr/bin/env bash
# One-command initialisation. Idempotent — safe to re-run.
#
# Does NOT install torch, transformers or chromadb. The agent index is BM25F over 6,000 lines
# and runs in 0.05 ms; see scripts/index_codebase.py for the measurement and the condition
# under which that decision should be revisited.
set -euo pipefail
cd "$(dirname "$0")"

echo "placedon-hr setup"
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

## The two things that outrank every feature
- [ ] H-2 — lawyer verifies 12 sections. One evening. Unlocks all 12 core questions.
- [ ] H-1 — ten customer conversations. Decides whether the buyer is HR or the CS/CA.

## Notes
MD

if [ -d frontend/node_modules ]; then
  echo "  frontend deps present"
else
  echo "  installing frontend deps (npm ci)"
  (cd frontend && npm ci --silent) || (cd frontend && npm install --silent)
fi

echo
python3 scripts/index_codebase.py | head -3
echo
./scripts/run_tests.sh | tail -3

cat <<'MD'

Ready.

  python3 -m uvicorn checker.app:app --reload --port 8000     # backend
  (cd frontend && npm run dev)                                # frontend :3000

  /start              open a session
  /build <feature>    full R-D-B-V-L loop
  /fix <bug>          reproduce, ratchet, fix, verify
  /research <topic>   research only, no code

  python3 scripts/search_memory.py "<question>"   ask the codebase first
  ./scripts/run_tests.sh                          every suite
MD
