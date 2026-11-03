"""Run the gateway/verbs suite: PYTHONPATH=. python3 gateway/verbs/__main__.py [--live]

The script entry the gate runs (scripts/run_tests.sh, scripts/suite_floors.json).
"""
from gateway.verbs.selftest import _live_smoke, _test

if __name__ == "__main__":
    import sys
    if "--live" in sys.argv:
        raise SystemExit(_live_smoke())
    _test()
