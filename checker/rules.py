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
# READ THIS BEFORE CHANGING THE NUMBER.
#
# s.4(1) contains NO threshold. Verbatim, from the ingested corpus:
#
#     "Every employer of a workplace shall, by an order in writing, constitute a
#      Committee to be known as the 'Internal Complaints Committee'"
#
# "Ten" appears nowhere in section 4. The ten-worker language lives in two other places:
#   s.2    — defining "unorganised sector": "...the number of such workers is less than ten"
#   s.6(1) — the Local Committee receives complaints "from establishments where the
#            Internal Committee has not been constituted due to having less than ten
#            workers or if the complaint is against the employer himself"
#
# So the universally-repeated "PoSH applies at 10+" is an INFERENCE from s.6 — the Act
# provides a Local Committee for establishments under ten, which implies those employers
# are not expected to constitute an IC. That is a reasonable reading. It is not what s.4
# says, and whether the s.4 duty attaches below ten is a question of interpretation.
#
# We therefore ship >= 10 as an UNVERIFIED INTERPRETATION, cited to its real source, and
# the report says so. Do not "fix" this by citing s.4(1) for the number — that citation
# does not support the claim, and an earlier version of this file made exactly that error.
IC_APPLIES = {"op": "gte", "field": "employee_count", "value": 10}

IC_THRESHOLD = 10
IC_TENURE_YEARS = 3          # s.4(2)(c)
PENALTY_INR = 50_000         # s.26 — "fine which may extend to fifty thousand rupees" (verified)

CITE_S4 = "s.4(1), PoSH Act 2013"
CITE_S4_TENURE = "s.4(2)(c), PoSH Act 2013"
CITE_S6 = "s.6(1), PoSH Act 2013"
CITE_S19 = "s.19, PoSH Act 2013"
CITE_S21 = "s.21/22, PoSH Act 2013"
CITE_S26 = "s.26, PoSH Act 2013"

# The threshold is an inference, and must be labelled as one wherever it is used.
CITE_THRESHOLD = f"{CITE_S6} (inferred — s.4 states no threshold)"

SRC_SECONDARY = "secondary sources; NOT lawyer-verified"
SRC_CORPUS = "ingested from India Code PDF; NOT lawyer-verified"


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
