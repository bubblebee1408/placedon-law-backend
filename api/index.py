"""
Vercel entry point.

The checker is a pure-compute app — no database, no LLM, no state — so it runs fine as a
serverless function. Vercel supplies the ASGI server; we only export `app`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.app import app  # noqa: E402,F401
