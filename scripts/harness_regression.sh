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
#   4. MISSING DEPENDENCY  a pinned package that is not installed
#                                               -> must be BLOCKED, exit 5, no suite run
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
REQ_DEV="requirements-dev.txt"
REQ_DEV_BAK="$(mktemp -t reqdev.XXXXXX)"
cp "$REQ_DEV" "$REQ_DEV_BAK"

cleanup() {
    rm -f "$CANARY_FAIL" "$CANARY_SILENT"
    # Case 4 edits a TRACKED file. Restoring it is not optional: a canary pin left behind
    # would BLOCK every subsequent run in this checkout.
    [ -f "$REQ_DEV_BAK" ] && cp "$REQ_DEV_BAK" "$REQ_DEV" && rm -f "$REQ_DEV_BAK"
}
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

# ── 4. a missing dependency is BLOCKED, not RED ──────────────────────────────
# Reported 2026-09-27: an environment without pypdf produced "checker/sarvam_model.py
# FAIL" with NO result line -- which reads as a broken suite and sends the reader to the
# wrong file. BLOCKED says the truer thing: nothing about the suite is known, because
# none of it ran.
echo
echo "case 4: a missing pinned dependency must be BLOCKED (exit 5), with no suite run"
printf 'zzz_canary_not_installable==1.0\n' >> "$REQ_DEV"
out=$(bash scripts/verify_green.sh 2>&1); rc=$?
[ "$rc" -eq 5 ] && check pass "verify_green exits 5 (environment not ready)" \
                || check fail "expected exit 5 for a missing dependency, got $rc"
grep -qE '^HARNESS_RESULT .*status=BLOCKED' <<<"$out" \
    && check pass "...and the runner printed status=BLOCKED" \
    || check fail "...but the runner did not print status=BLOCKED"
grep -q 'zzz_canary_not_installable' <<<"$out" \
    && check pass "...naming the package that is missing" \
    || check fail "...but did not name the missing package"
grep -q 'ENVIRONMENT NOT READY' <<<"$out" \
    && check pass "...and says the environment is what is wrong" \
    || check fail "...but did not say the environment is what is wrong"
grep -qE '^HARNESS_RESULT .*status=RED' <<<"$out" \
    && check fail "a missing dependency was reported as RED -- that is the bug" \
    || check pass "...and it is NOT reported as RED"
cp "$REQ_DEV_BAK" "$REQ_DEV"
grep -q 'zzz_canary' "$REQ_DEV" \
    && check fail "the canary pin survived in $REQ_DEV" \
    || check pass "$REQ_DEV restored"

echo
echo "$ok/$((ok+fail)) passed"
[ "$fail" -eq 0 ] || exit 1
