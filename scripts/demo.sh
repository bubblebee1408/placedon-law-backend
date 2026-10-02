#!/usr/bin/env bash
# P1: one command runs the whole product on synthetic data and prints pass or fail.
# The orchestration is in scripts/demo.py -- bash capturing exit codes, timing out children
# and parsing their output is error-prone, and demo.py --test can be run by the gate.
set -u
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec env PYTHONPATH="$root" python3 "$root/scripts/demo.py" "$@"
