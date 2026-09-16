#!/usr/bin/env bash
# The single oracle for "is the suite green?". Nothing else may decide.
#
# WHY THIS EXISTS
# run_tests.sh was never the bug. It captures each suite's real exit code, has a
# count_mismatch guard for a suite that prints "9/10 passed" while exiting 0, and ends
# in `exit $fails`. It has always told the truth. Both false greens in this repo came
# from the CALL SITE:
#
#   ./scripts/run_tests.sh | tail -8        the pipeline's status became tail's -> 0
#   ./scripts/run_tests.sh > out 2>&1 &     the `&` detached it; the shell returned 0
#                                           immediately while the suite still ran
#
# Both were then read as green by a human looking at prose. So the fix is not another
# guard inside the runner. It is a machine-parseable contract (HARNESS_RESULT) plus
# this file, which is the only thing permitted to answer the question.
#
# RULES THIS FILE OBEYS
#   - no `&`, no background, no detach
#   - the runner's exit code is read from the runner itself, never from a wrapper
#   - no pipe whose status could stand in for the runner's
#   - any parse failure is NOT GREEN. Silence is never success.
#
# EXIT CODES
#   0  verified green
#   1  suite is red
#   3  no HARNESS_RESULT line -- runner did not finish, or is the wrong version
#   4  contradiction between exit code and reported counts
set -uo pipefail
cd "$(dirname "$0")/.."

started=$(date +%s)

# Captured, not piped. The assignment's status IS the runner's status.
output=$(bash scripts/run_tests.sh 2>&1)
runner_status=$?

printf '%s\n' "$output"

# awk END rather than `tail`: this file does not use tail anywhere, deliberately.
line=$(awk '/^HARNESS_RESULT /{last=$0} END{print last}' <<<"$output")

if [ -z "$line" ]; then
    cat >&2 <<MSG

verify_green: NOT GREEN -- no HARNESS_RESULT line in the output.
  The runner did not reach its final line (killed, timed out, crashed), or this is an
  older run_tests.sh. An absent result is a failure, never a pass.
  runner exit code was: $runner_status
MSG
    exit 3
fi

suites=$(sed -n 's/.*suites=\([0-9][0-9]*\).*/\1/p' <<<"$line")
failed=$(sed -n 's/.*failed=\([0-9][0-9]*\).*/\1/p' <<<"$line")
status=$(sed -n 's/.*status=\([A-Z][A-Z]*\).*/\1/p' <<<"$line")

if [ -z "$suites" ] || [ -z "$failed" ] || [ -z "$status" ]; then
    echo "verify_green: NOT GREEN -- could not parse: $line" >&2
    exit 3
fi

# A runner that exits 0 while reporting failures (or the reverse) is broken in exactly
# the way this file exists to catch. Refuse both directions rather than trusting either.
if { [ "$runner_status" -eq 0 ] && [ "$failed" -ne 0 ]; } ||
   { [ "$runner_status" -ne 0 ] && [ "$failed" -eq 0 ]; }; then
    echo "verify_green: CONTRADICTION -- runner exited $runner_status but reported failed=$failed" >&2
    echo "verify_green: refusing to call this either way." >&2
    exit 4
fi

elapsed=$(( $(date +%s) - started ))

if [ "$runner_status" -eq 0 ] && [ "$failed" -eq 0 ] && [ "$status" = "GREEN" ]; then
    echo "verify_green: VERIFIED GREEN -- $suites suites, 0 failed, ${elapsed}s"
    exit 0
fi

echo "verify_green: NOT GREEN -- $failed of $suites suites failed (status=$status, ${elapsed}s)" >&2
exit 1
