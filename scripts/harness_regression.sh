#!/usr/bin/env bash
# Proof that a failing suite really does turn the harness RED.
#
# This is the file that makes the masking bug unable to recur. Everything else here is
# a claim; this is the check. It runs three cases:
#
#   1. POSITIVE CONTROL   clean tree            -> must be GREEN, exit 0
#   2. HARD FAILURE       a suite exiting 1     -> must be RED,   exit non-zero
#   3. SILENT FAILURE     a suite printing "0/1 passed" while exiting 0
#                                               -> must be RED,   exit non-zero
#
# Case 1 is not optional. A regression test that only asserts RED would pass against a
# runner that always says RED, which is useless in the other direction.
#
# Case 3 is the earlier incident in this repo: eight modules once defined _test() with
# no `raise SystemExit(1)`, so four real failures never reached an exit code and the
# sweep printed "all suites green" over them. run_tests.sh's count_mismatch guard is
# what catches it; this proves that guard still works.
#
# NOT part of run_tests.sh -- it invokes run_tests.sh, so including it would recurse.
# Run it by hand, or in CI, after any change to the harness. Three full sweeps.
set -uo pipefail
cd "$(dirname "$0")/.."

CANARY_FAIL="scripts/_canary_hard_fail.py"
CANARY_SILENT="scripts/_canary_silent_fail.py"

cleanup() { rm -f "$CANARY_FAIL" "$CANARY_SILENT"; }
trap cleanup EXIT INT TERM      # the canaries must never survive this script

ok=0; fail=0
check() {
    if [ "$1" = "pass" ]; then ok=$((ok+1)); echo "  [ok]   $2"
    else fail=$((fail+1)); echo "  [FAIL] $2"; fi
}

echo "harness_regression -- three full sweeps, this takes a few minutes"
echo

# ── 1. positive control ──────────────────────────────────────────────────────
echo "case 1: clean tree must verify GREEN"
out=$(bash scripts/verify_green.sh 2>&1); rc=$?
if [ "$rc" -ne 0 ]; then
    echo "  [FAIL] the tree is not green to begin with -- fix that before trusting"
    echo "         anything below. verify_green exited $rc"
    printf '%s\n' "$out" | grep -E 'FAIL|MISSING|HARNESS_RESULT|verify_green' | head -8
    exit 1
fi
check pass "a clean tree verifies GREEN (exit 0)"
grep -qE '^HARNESS_RESULT .*status=GREEN' <<<"$out" \
    && check pass "...and prints status=GREEN" \
    || check fail "...but did not print status=GREEN"

# ── 2. a suite that exits non-zero ───────────────────────────────────────────
echo
echo "case 2: a hard-failing suite must turn it RED"
cat > "$CANARY_FAIL" <<'PY'
"""Deliberate failure, injected by scripts/harness_regression.sh. Deleted afterwards."""
print("  [FAIL] canary: this suite fails on purpose")
print("\n0/1 passed")
raise SystemExit(1)
PY
out=$(HARNESS_EXTRA_SUITE="$CANARY_FAIL" bash scripts/verify_green.sh 2>&1); rc=$?
[ "$rc" -ne 0 ] && check pass "verify_green exits non-zero ($rc)" \
                || check fail "verify_green exited 0 on a failing suite -- THE BUG IS BACK"
grep -qE '^HARNESS_RESULT .*status=RED' <<<"$out" \
    && check pass "...and the runner printed status=RED" \
    || check fail "...but the runner did not print status=RED"
grep -qE '^HARNESS_RESULT .*failed=[1-9]' <<<"$out" \
    && check pass "...with a non-zero failed count" \
    || check fail "...but failed= was zero"
rm -f "$CANARY_FAIL"

# ── 3. a suite that exits 0 while its own counts say otherwise ───────────────
echo
echo "case 3: a suite exiting 0 while printing '0/1 passed' must ALSO turn it RED"
cat > "$CANARY_SILENT" <<'PY'
"""Exits 0 while reporting a failed check -- the 'silent failure' shape that once hid
four real failures behind 'all suites green'. Injected by harness_regression.sh."""
print("  [FAIL] canary: failed, but exiting 0 anyway")
print("\n0/1 passed")
PY
out=$(HARNESS_EXTRA_SUITE="$CANARY_SILENT" bash scripts/verify_green.sh 2>&1); rc=$?
[ "$rc" -ne 0 ] && check pass "verify_green exits non-zero ($rc) on a silent failure" \
                || check fail "a suite exiting 0 with failing counts was accepted -- count_mismatch is broken"
grep -qE '^HARNESS_RESULT .*status=RED' <<<"$out" \
    && check pass "...and the runner printed status=RED" \
    || check fail "...but the runner did not print status=RED"
rm -f "$CANARY_SILENT"

echo
echo "$ok/$((ok+fail)) passed"
[ "$fail" -eq 0 ] || exit 1
