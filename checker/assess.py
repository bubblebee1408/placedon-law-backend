"""
Turn a company profile into a list of findings.

No LLM. `applicability.py` decides; this file arranges the result into report lines. That is why
the free checker costs ₹0 to run (DECISIONS D-3) — the whole path is deterministic Python.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from applicability import CompanyProfile, Result, evaluate  # noqa: E402
from jurisdiction import Resolution, resolve  # noqa: E402

from .rules import (  # noqa: E402
    ANNUAL_RETURN_DEADLINE, CITE_S4, CITE_S4_TENURE, CITE_S19, CITE_S21, CITE_S26,
    IC_APPLIES, IC_TENURE_YEARS, IC_THRESHOLD, PENALTY_INR, SRC_SECONDARY, Finding,
)

_ORDER = {"critical": 0, "unknown": 1, "warning": 2, "good": 3}


def assess(
    profile: CompanyProfile,
    *,
    has_ic: bool | None,
    ic_constituted_on: date | None,
    has_policy: bool | None,
    filed_return: bool | None,
) -> tuple[list[Finding], str]:
    """Returns (findings, headline). Headline is plain, not scored — no invented maturity number."""
    applies, trace = evaluate(IC_APPLIES, profile)
    total_workers = profile.employee_count + profile.contractor_count
    findings: list[Finding] = []

    if applies is Result.DOES_NOT_APPLY:
        short_by = IC_THRESHOLD - profile.employee_count
        findings.append(Finding(
            title="PoSH does not require an Internal Committee yet",
            severity="good",
            detail=(
                f"You have {profile.employee_count} employees. The Internal Committee duty "
                f"starts at {IC_THRESHOLD}. You are {short_by} "
                f"{'hire' if short_by == 1 else 'hires'} away — the duty attaches as soon as "
                f"you cross it, not at the end of a financial year."
            ),
            citation=CITE_S4,
            source=SRC_SECONDARY,
        ))
        if profile.contractor_count:
            findings.append(Finding(
                title="Your contractor count may change this answer",
                severity="unknown",
                detail=(
                    f"You have {profile.employee_count} employees plus "
                    f"{profile.contractor_count} contract workers ({total_workers} people on "
                    f"site). Whether contract workers count toward the threshold is exactly the "
                    f"kind of question we will not answer until a lawyer has verified it. "
                    f"Treat {IC_THRESHOLD} as close."
                ),
                citation=CITE_S4,
                source=SRC_SECONDARY,
            ))
        return _sorted(findings), "PoSH's Internal Committee duty has not started for you yet."

    # ── The duty applies ────────────────────────────────────────────────────
    if has_ic is not True:
        findings.append(Finding(
            title="No Internal Committee",
            severity="critical",
            detail=(
                f"You have {profile.employee_count} employees, so an Internal Committee is "
                f"required. Not having one is punishable by a fine of up to "
                f"₹{PENALTY_INR:,}, and repeat default can put your business licence at risk."
            ),
            citation=f"{CITE_S4}; penalty {CITE_S26}",
            source=SRC_SECONDARY,
            action="This is the one to fix first.",
        ))
    else:
        detail = "You have an Internal Committee."
        severity: str = "good"
        if ic_constituted_on:
            years = (profile.as_of - ic_constituted_on).days / 365.25
            if years > IC_TENURE_YEARS:
                severity = "warning"
                detail = (
                    f"Your Internal Committee was constituted on "
                    f"{ic_constituted_on:%d %b %Y} — about {years:.1f} years ago. Members hold "
                    f"office for a term not exceeding {IC_TENURE_YEARS} years, so this one "
                    f"looks due for reconstitution."
                )
            else:
                detail = (
                    f"Constituted {ic_constituted_on:%d %b %Y}. Reconstitution is due by "
                    f"{ic_constituted_on.replace(year=ic_constituted_on.year + IC_TENURE_YEARS):%d %b %Y}."
                )
        findings.append(Finding(
            title="Internal Committee",
            severity=severity,  # type: ignore[arg-type]
            detail=detail,
            citation=CITE_S4_TENURE if ic_constituted_on else CITE_S4,
            source=SRC_SECONDARY,
        ))

    if has_policy is not True:
        findings.append(Finding(
            title="No written PoSH policy on display",
            severity="warning",
            detail=(
                "The employer must display the penal consequences of sexual harassment and the "
                "order constituting the Internal Committee at a conspicuous place at the "
                "workplace."
            ),
            citation=CITE_S19,
            source=SRC_SECONDARY,
        ))
    else:
        findings.append(Finding(
            title="PoSH policy exists",
            severity="good",
            detail="You told us you have a written policy. We have not read it.",
            citation=CITE_S19,
            source=SRC_SECONDARY,
        ))

    findings.append(_annual_return(profile, filed_return))

    critical = sum(f.severity == "critical" for f in findings)
    unknown = sum(f.severity == "unknown" for f in findings)
    headline = (
        f"PoSH applies to you. "
        + (f"{critical} thing needs fixing now. " if critical == 1
           else f"{critical} things need fixing now. " if critical else "Nothing is critical. ")
        + (f"{unknown} we could not answer honestly." if unknown else "")
    ).strip()
    return _sorted(findings), headline


def _annual_return(profile: CompanyProfile, filed_return: bool | None) -> Finding:
    """
    The centrepiece. The deadline is district-set; we do not hold Karnataka's, so we abstain
    rather than repeat the widely-quoted 31 January. This is the product's whole thesis,
    visible on the first screen a stranger ever sees.
    """
    res = resolve(ANNUAL_RETURN_DEADLINE, profile.state, profile.districts)

    if res.status is Resolution.RESOLVED:
        return Finding(
            title=f"Annual return — due {res.record.payload}" if res.record else "Annual return",
            severity="warning" if filed_return is not True else "good",
            detail=(
                f"Your District Officer has notified {res.record.payload} as the deadline."
                if res.record else ""
            ) + ("" if filed_return is True else " You told us you have not filed it."),
            citation=res.citation or CITE_S21,
            source=SRC_SECONDARY,
        )

    return Finding(
        title="Annual return — we will not guess your deadline",
        severity="unknown",
        detail=(
            "An annual report goes to the District Officer, but the date is fixed by that "
            "officer, not nationally — Gurugram notified 28 February, while most districts use "
            "31 January. We do not hold the notification for your district, so we are not going "
            "to tell you a date. Most tools will confidently say 31 January. That is a "
            "generalisation, not a rule, and acting on it is how you miss a deadline you "
            "thought you had met."
        ),
        citation=res.citation or CITE_S21,
        source=SRC_SECONDARY,
        action="Ask your District Officer, and tell us what they say — we will add it.",
    )


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: _ORDER[f.severity])
