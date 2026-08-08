"""
Are the pinned dependencies importable? Exit 0 if yes.

Reads requirements.txt rather than a hand-kept list — setup.sh carried one that had already
drifted from the pins it was meant to guarantee.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Distribution name -> import name, where they differ.
IMPORT_NAME = {"python-multipart": "multipart", "Jinja2": "jinja2", "PyYAML": "yaml",
               "beautifulsoup4": "bs4", "Pillow": "PIL"}


def requirements() -> list[str]:
    names: list[str] = []
    for f in ("requirements.txt", "requirements-dev.txt"):
        p = ROOT / f
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            names.append(re.split(r"[=<>~!\[;]", line, maxsplit=1)[0].strip())
    return names


def main() -> int:
    missing = [n for n in requirements()
               if not importlib.util.find_spec(IMPORT_NAME.get(n, n.replace("-", "_")))]
    if missing:
        print("missing: " + " ".join(missing), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
