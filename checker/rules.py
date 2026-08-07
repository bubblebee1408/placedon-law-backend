"""
PoSH obligations, encoded.

EVERY rule here has `verified_by = None`. Nothing in this file has been checked by an employment
lawyer, and the checker says so on every screen. That is not a disclaimer bolted on — it is the
honest state of the corpus, and shipping it visibly is the point (BACKLOG H-2 removes it).

Sources are secondary and recorded per-rule. The annual-return deadline is the one that matters
most and is the one we deliberately refuse to answer: it is set by the District Officer, and we
do not hold Karnataka's notification (BACKLOG H-3). See jurisdiction.py.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jurisdiction import Scoped  # noqa: E402

Severity = Literal["critical", "warning", "good", "unknown"]


@dataclass(frozen=True)
class Finding:
    """One line of the report. `citation` is mandatory on the compliance track."""
    title: str
    severity: Severity
    detail: str
    citation: str | None = None
    source: str | None = None
    action: str | None = None

    def __post_init__(self) -> None:
        if self.severity in ("critical", "warning", "good") and not self.citation:
            raise ValueError(f"compliance finding {self.title!r} has no citation")


# ── The applicability trigger ────────────────────────────────────────────────
# s.4(1): "Every employer ... shall ... constitute a Committee ... where 10 or more
# employees are employed." Boundary is >= 10, not > 10. An off-by-one here is a
# customer's ₹50,000.
IC_APPLIES = {"op": "gte", "field": "employee_count", "value": 10}

IC_THRESHOLD = 10
IC_TENURE_YEARS = 3          # s.4(2)(c) — "not exceeding three years"
PENALTY_INR = 50_000         # s.26 — "fine which may extend to fifty thousand rupees"

CITE_S4 = "s.4(1), PoSH Act 2013"
CITE_S4_TENURE = "s.4(2)(c), PoSH Act 2013"
CITE_S19 = "s.19, PoSH Act 2013"
CITE_S21 = "s.21/22, PoSH Act 2013"
CITE_S26 = "s.26, PoSH Act 2013"

SRC_SECONDARY = "secondary sources; NOT lawyer-verified"


# ── The annual-return deadline, jurisdiction-scoped ──────────────────────────
# This is the honest centrepiece. Research found the deadline is fixed by the District
# Officer — Gurugram notified 28 February where most districts use 31 January. We could
# not find Karnataka's. So for a Bengaluru company this ABSTAINS rather than guessing,
# and the report says why.
ANNUAL_RETURN_DEADLINE = [
    Scoped(
        "IN",
        "no single national date — fixed by the District Officer",
        district_scoped=True,
        evidence=f"{CITE_S21}; deadline fixed by the District Officer",
    ),
    Scoped(
        "IN-HR-GGN",
        "28 February",
        district_scoped=True,
        evidence="Gurugram District Officer notification (revised from 30 April)",
    ),
]


STATES = [
    ("IN-KA", "Karnataka"),
    ("IN-MH", "Maharashtra"),
    ("IN-DL", "Delhi"),
    ("IN-TG", "Telangana"),
    ("IN-TN", "Tamil Nadu"),
    ("IN-HR", "Haryana"),
    ("IN-OTHER", "Somewhere else"),
]

DISTRICTS = {
    "IN-KA": [("IN-KA-BLR", "Bengaluru Urban"), ("", "Elsewhere in the state")],
    "IN-HR": [("IN-HR-GGN", "Gurugram"), ("", "Elsewhere in the state")],
}

INDUSTRIES = [
    ("it_ites", "IT / SaaS"),
    ("factory", "Manufacturing"),
    ("shop_or_commercial", "Retail / Services"),
    ("other", "Something else"),
]
