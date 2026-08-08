#!/usr/bin/env python3
"""Wrapper. The implementation lives in scripts/search_memory.py — one copy, no drift."""
import runpy, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.argv[0] = str(ROOT / "scripts/search_memory.py")
runpy.run_path(str(ROOT / "scripts/search_memory.py"), run_name="__main__")
