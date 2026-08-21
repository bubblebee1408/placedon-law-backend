#!/usr/bin/env bash
# Run every self-testing module.
#
# Exists because these modules import as `checker.x` but are run as files, so a bare
# `python3 checker/as_of.py` dies with ModuleNotFoundError. That looked like a silent pass in an
# ad-hoc loop once -- the suite had not run at all. PYTHONPATH is set here so it cannot recur.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"

suites=(
  checker/amendment.py
  checker/as_of.py
  checker/derived_date.py
  checker/legal_ref.py
  checker/provenance.py
  checker/section_index.py
  checker/mvp_freeze.py
  checker/ss/defects.py
  applicability.py
)

fails=0
for s in "${suites[@]}"; do
  [ -f "$s" ] || { printf '%-28s %s\n' "$s" "MISSING"; fails=$((fails+1)); continue; }
  out=$(python3 "$s" 2>&1); rc=$?
  res=$(printf '%s' "$out" | grep -oE '[0-9]+/[0-9]+ passed' | tail -1)
  if [ $rc -ne 0 ]; then
    printf '%-28s FAIL  %s\n' "$s" "${res:-no result line}"
    printf '%s\n' "$out" | grep -E '^\[FAIL\]|Error|Traceback' | head -4 | sed 's/^/      /'
    fails=$((fails+1))
  else
    printf '%-28s ok    %s\n' "$s" "${res:-(no count)}"
  fi
done

echo
[ $fails -eq 0 ] && echo "all suites green" || echo "$fails suite(s) failing"
exit $fails
