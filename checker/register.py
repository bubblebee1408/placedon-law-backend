"""
Read the notified-date register and say what we know about a district — with its provenance.

## Why this is a module and not three lines inside ask_engine

The annual-return deadline is the one question where every source on the Indian internet is
confidently wrong. "31 January" appears nowhere in the fourteen PoSH Rules; s.21 delegates timing
to what "may be prescribed" and the Rules prescribe nothing; District Officers set their own dates
and at least one has notified 28 February. So the honest answer is district-specific, and for most
districts the honest answer today is *"we asked and nobody has replied yet"*.

That last sentence is a product feature, not a gap. It is the only thing here a competitor cannot
copy without doing the same work, and it is worthless the moment anyone is tempted to fill a blank
row with a plausible date. Hence one rule, enforced here and in `scripts/verify.py`:

    a date exists in the register only alongside the words it came from.

`describe()` never returns a date without also returning its source. There is no code path that
produces one.

## Failure is loud

An unknown jurisdiction code raises. It does not return None-and-carry-on, because a silent miss
here means the caller falls back to a generic answer — and the generic answer in this domain is
the fabricated one. `jurisdiction.py` makes the same argument about district→state fallback:
falling back *is* the bug.

Run: python3 checker/register.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "corpus/reference/notified_dates.json"

# So `python3 checker/register.py` works the same way the other module suites do.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class UnknownDistrict(KeyError):
    """Raised for a jurisdiction code the register does not hold. Never swallowed."""


@dataclass(frozen=True)
class DistrictStatus:
    """One district's row, as recorded. `notified_date` is never set without `reply_verbatim`."""

    jurisdiction: str
    district: str
    status: str
    asked_on: str | None = None
    replied_on: str | None = None
    notified_date: str | None = None
    reply_verbatim: str | None = None

    @property
    def has_answer(self) -> bool:
        """True when a District Officer has actually told us something."""
        return self.status in {"DATE_NOTIFIED", "NONE_NOTIFIED"}


@lru_cache(maxsize=1)
def _rows() -> dict[str, DistrictStatus]:
    if not REGISTER.exists():
        return {}
    doc = json.loads(REGISTER.read_text())
    return {r["jurisdiction"]: DistrictStatus(
        jurisdiction=r["jurisdiction"], district=r["district"], status=r["status"],
        asked_on=r.get("asked_on"), replied_on=r.get("replied_on"),
        notified_date=r.get("notified_date"), reply_verbatim=r.get("reply_verbatim"),
    ) for r in doc.get("districts", [])}


def lookup(code: str) -> DistrictStatus:
    """The district's row. Raises UnknownDistrict rather than returning a default."""
    rows = _rows()
    if code not in rows:
        raise UnknownDistrict(
            f"{code!r} is not in the notified-date register. Add it via "
            f"scripts/build_register.py rather than answering without it — the generic answer "
            f"for this question is the fabricated one."
        )
    return rows[code]


def describe(code: str) -> tuple[str, dict | None]:
    """
    A sentence a person can act on, and the source it rests on.

    Returns `(sentence, source)`. `source` is None exactly when there is nothing to cite, which
    is exactly when the sentence promises nothing.
    """
    r = lookup(code)

    if r.status == "DATE_NOTIFIED":
        # Guarded twice over. verify.py refuses this state in the file; this refuses it in memory,
        # because a date reaching a user without its source is the failure that matters.
        if not (r.reply_verbatim or "").strip():
            raise ValueError(f"{code}: DATE_NOTIFIED without reply_verbatim — refusing to answer.")
        return (
            f"The District Officer for {r.district} notified {r.notified_date} "
            f"(replied {r.replied_on}).",
            {"kind": "district_officer_reply", "district": r.district,
             "replied_on": r.replied_on, "quote": r.reply_verbatim},
        )

    if r.status == "NONE_NOTIFIED":
        if not (r.reply_verbatim or "").strip():
            raise ValueError(f"{code}: NONE_NOTIFIED without reply_verbatim — refusing to answer.")
        return (
            f"The District Officer for {r.district} confirmed no date has been notified there "
            f"(replied {r.replied_on}).",
            {"kind": "district_officer_reply", "district": r.district,
             "replied_on": r.replied_on, "quote": r.reply_verbatim},
        )

    if r.status == "NO_REPLY":
        return (
            f"We asked the District Officer for {r.district} on {r.asked_on} and have had no "
            f"reply. No date is prescribed in the Rules, so we cannot tell you one.",
            None,
        )

    if r.status == "ASKED":
        return (
            f"We wrote to the District Officer for {r.district} on {r.asked_on}. No reply yet.",
            None,
        )

    return (
        f"We have not yet asked the District Officer for {r.district}. No date is prescribed in "
        f"the PoSH Rules, and we will not repeat one we cannot source.",
        None,
    )


# --------------------------------------------------------------------------------------------
_pass = _fail = 0


def check(name: str, got, want) -> None:
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}\n        got  {got!r}\n        want {want!r}")


def _fixture(**kw) -> DistrictStatus:
    base = dict(jurisdiction="IN-KA-TST", district="Testville", status="UNASKED")
    return DistrictStatus(**{**base, **kw})


def _suite() -> int:
    import checker.register as mod

    real = mod._rows
    try:
        rows: dict[str, DistrictStatus] = {}
        mod._rows = lambda: rows                                        # type: ignore[assignment]

        rows["IN-KA-A"] = _fixture(jurisdiction="IN-KA-A", district="Alpha", status="UNASKED")
        s, src = mod.describe("IN-KA-A")
        check("UNASKED names the district and promises nothing", "have not yet asked" in s, True)
        check("UNASKED cites nothing", src, None)
        check("UNASKED says why we won't guess", "will not repeat one we cannot source" in s, True)

        rows["IN-KA-B"] = _fixture(jurisdiction="IN-KA-B", district="Beta", status="ASKED",
                                   asked_on="2026-08-13")
        s, src = mod.describe("IN-KA-B")
        check("ASKED shows the date we wrote", "2026-08-13" in s, True)
        check("ASKED cites nothing", src, None)

        rows["IN-KA-C"] = _fixture(jurisdiction="IN-KA-C", district="Gamma", status="NO_REPLY",
                                   asked_on="2026-07-01")
        s, src = mod.describe("IN-KA-C")
        check("NO_REPLY is a finding, not an error", "no reply" in s.lower(), True)
        check("NO_REPLY still refuses to state a date",
              "cannot tell you one" in s, True)

        rows["IN-KA-D"] = _fixture(jurisdiction="IN-KA-D", district="Delta", status="DATE_NOTIFIED",
                                   asked_on="2026-07-01", replied_on="2026-07-20",
                                   notified_date="28 February",
                                   reply_verbatim="The report is due by 28th February each year.")
        s, src = mod.describe("IN-KA-D")
        check("DATE_NOTIFIED states the date", "28 February" in s, True)
        check("DATE_NOTIFIED carries a source", src is not None, True)
        check("the source is the officer's own words",
              src["quote"], "The report is due by 28th February each year.")

        rows["IN-KA-E"] = _fixture(jurisdiction="IN-KA-E", district="Epsilon",
                                   status="NONE_NOTIFIED", asked_on="2026-07-01",
                                   replied_on="2026-07-22",
                                   reply_verbatim="No date has been notified for this district.")
        s, src = mod.describe("IN-KA-E")
        check("NONE_NOTIFIED is answerable and sourced", src is not None, True)
        check("NONE_NOTIFIED does not invent a date", "January" not in s, True)

        # The two failures that matter.
        rows["IN-KA-F"] = _fixture(jurisdiction="IN-KA-F", district="Zeta", status="DATE_NOTIFIED",
                                   asked_on="2026-07-01", replied_on="2026-07-20",
                                   notified_date="31 January", reply_verbatim=None)
        try:
            mod.describe("IN-KA-F")
            check("a date without its reply is refused in memory too", "no raise", "ValueError")
        except ValueError:
            check("a date without its reply is refused in memory too", True, True)

        try:
            mod.lookup("IN-KA-NOPE")
            check("unknown district raises rather than defaulting", "no raise", "UnknownDistrict")
        except mod.UnknownDistrict:
            check("unknown district raises rather than defaulting", True, True)

        # Every status the register can hold must have a branch. A status with no branch would
        # fall through to the UNASKED wording and quietly misdescribe the district.
        VALID = {"UNASKED", "ASKED", "DATE_NOTIFIED", "NONE_NOTIFIED", "NO_REPLY"}
        described = set()
        for st in VALID:
            code = f"IN-KA-Z{len(described)}"
            rows[code] = _fixture(jurisdiction=code, district="Probe", status=st,
                                  asked_on="2026-01-01", replied_on="2026-01-02",
                                  notified_date="1 March" if st == "DATE_NOTIFIED" else None,
                                  reply_verbatim="quoted" if st in {"DATE_NOTIFIED",
                                                                    "NONE_NOTIFIED"} else None)
            described.add(mod.describe(code)[0])
        check("all five statuses produce distinct wording", len(described), len(VALID))
    finally:
        mod._rows = real                                                # type: ignore[assignment]

    print(f"\n  {_pass} passed, {_fail} failed")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(_suite())
