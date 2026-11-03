"""Run the store suite: PYTHONPATH=. python3 gateway/store/__main__.py

The script entry the gate runs (scripts/run_tests.sh, scripts/suite_floors.json).
"""
from gateway.store.selftest import _test

if __name__ == "__main__":
    _test()
