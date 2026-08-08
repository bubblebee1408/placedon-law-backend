#!/usr/bin/env python3
"""Wrapper. The implementation lives in scripts/index_codebase.py — one copy, no drift."""
import runpy, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.argv[0] = str(ROOT / "scripts/index_codebase.py")
runpy.run_path(str(ROOT / "scripts/index_codebase.py"), run_name="__main__")
