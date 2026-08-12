"""
Build and maintain the notified-date register.

## What this is

Every guide to PoSH compliance in India ends the deadline question the same way: *"the safest
approach is to check the current notification issued by your specific District Officer."* It is
told to the customer as homework. Meanwhile "31 January" is repeated as though it were statutory —
it appears nowhere in the Rules — and Gurugram's District Officer notifies 28 February, which
proves the variation is real and consequential.

Nobody has done the asking. This register is the asking, written down.

It starts as 31 rows with no dates: every district in Karnataka, from the MWCD's own SHe-Box
District Officer directory, each marked UNASKED. Rows gain a date only when a District Officer
supplies one, in their own words, which are stored alongside it.

## The rule

A date is recordable only with the reply it came from. That is the same rule `verified_by`
enforces on the corpus, applied to a second kind of claim, and for the same reason: the register's
entire worth is that a reader can check it. Filling one gap with a plausible date read off a blog
would make it folklore with our name on it, and would be undetectable afterwards.

**"Asked, no reply" is a first-class value, not a gap.** It is also, commercially, the more
differentiating one — it is a fact about the district that nobody else has bothered to establish.

`scripts/verify.py::_register_dates_have_sources` refuses any violation.

    python3 scripts/build_register.py            # report; create the register if absent
    python3 scripts/build_register.py --mark-asked IN-KA-BLR --on 2026-08-12
    python3 scripts/build_register.py --record IN-KA-BLR --date "31 January" \
        --on 2026-08-20 --reply "The annual report is to be submitted by 31st January."
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICERS = ROOT / "corpus/reference/district_officers.json"
REGISTER = ROOT / "corpus/reference/notified_dates.json"

# ISO 3166-2 stops at the state, so district codes are our extension. jurisdiction.py already
# expects three parts and treats a two-part code as a state — which it must never silently
# fall back to for a district-scoped obligation.
STATE_CODE = {"Karnataka": "IN-KA"}

# Districts that already have a code in use elsewhere. These are NOT generated, because a
# generated code would silently disagree with them.
#
# The first build produced IN-KA-BENGA for Bengaluru Urban — three letters were already taken by
# Bengaluru Rural, which sorts first — while applicability.py, jurisdiction.py, the frontend's
# checker-form and shared/types.ts all use IN-KA-BLR. Nothing would have crashed. The register
# would simply never have matched a lookup for the one district that matters most: the one the
# drafted letter is addressed to. A register nothing can query is worse than no register, because
# it looks like it works.
ESTABLISHED = {"Bengaluru Urban": "IN-KA-BLR"}


def _slug(district: str) -> str:
    """A stable three-letter suffix. Deterministic, so codes never move between runs."""
    ascii_name = unicodedata.normalize("NFKD", district).encode("ascii", "ignore").decode()
    letters = re.sub(r"[^A-Za-z]", "", ascii_name).upper()
    return letters[:3]


def _codes(officers: list[dict]) -> dict[str, str]:
    """district -> jurisdiction code, with collisions resolved rather than silently shared."""
    out: dict[str, str] = {}
    used: set[str] = set()
    # Claim the established codes first so generation cannot take their letters.
    for name, code in ESTABLISHED.items():
        out[name], _ = code, used.add(code)
    for o in sorted(officers, key=lambda x: x["district"]):
        if o["district"] in out:
            continue
        base = _slug(o["district"])
        suffix, n = base, 1
        while f"{STATE_CODE[o['state']]}-{suffix}" in used:
            n += 1
            # Widen rather than number: BEN/BENG reads better than BEN2 in a citation.
            ascii_name = re.sub(r"[^A-Za-z]", "", o["district"]).upper()
            suffix = ascii_name[: 3 + n] or f"{base}{n}"
            if suffix == base:
                suffix = f"{base}{n}"
        code = f"{STATE_CODE[o['state']]}-{suffix}"
        used.add(code)
        out[o["district"]] = code
    return out


def build() -> dict:
    officers = json.loads(OFFICERS.read_text())["officers"]
    codes = _codes(officers)
    rows = [{
        "jurisdiction": codes[o["district"]],
        "state": o["state"],
        "district": o["district"],
        "officer": o.get("officer"),
        "email": o.get("email"),
        "status": "UNASKED",
        "asked_on": None,
        "replied_on": None,
        "notified_date": None,
        "reply_verbatim": None,
    } for o in sorted(officers, key=lambda x: x["district"])]

    return {
        "instrument": {
            "title": "Notified PoSH annual-return dates, by district",
            "what_this_is": (
                "What each District Officer says, in their own words, about the date on which the "
                "annual report under s.21 of the PoSH Act is to be submitted in their district."
            ),
            "WHAT_THIS_IS_NOT": (
                "Not a national deadline — there is no national deadline. s.21 delegates timing "
                "to what 'may be prescribed' and the PoSH Rules 2013 prescribe no date; the words "
                "'January', '31' and 'Form C' appear nowhere in all fourteen rules. A row without "
                "a reply is not an omission to be filled in. It is the honest state of that "
                "district, and it stays that way until an officer answers."
            ),
            "officers_source": json.loads(OFFICERS.read_text()).get("source"),
            "coverage": f"{len(rows)} districts — complete coverage of Karnataka",
            "built_on": str(date.today()),
        },
        "districts": rows,
    }


def _load() -> dict:
    return json.loads(REGISTER.read_text()) if REGISTER.exists() else build()


def _row(doc: dict, code: str) -> dict:
    for r in doc["districts"]:
        if r["jurisdiction"] == code:
            return r
    raise SystemExit(f"REFUSED: no district with jurisdiction {code!r} in the register.")


def _save(doc: dict) -> None:
    REGISTER.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def report(doc: dict) -> None:
    counts: dict[str, int] = {}
    for r in doc["districts"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"  {doc['instrument']['coverage']}\n")
    for st in ("DATE_NOTIFIED", "NONE_NOTIFIED", "NO_REPLY", "ASKED", "UNASKED"):
        if st in counts:
            print(f"    {st:<15} {counts[st]:>3}")
    answered = counts.get("DATE_NOTIFIED", 0) + counts.get("NONE_NOTIFIED", 0)
    asked = sum(counts.get(k, 0) for k in ("ASKED", "NO_REPLY", "DATE_NOTIFIED", "NONE_NOTIFIED"))
    total = len(doc["districts"])
    print(f"\n  {asked} of {total} districts asked · {answered} answered.")
    # Three states, three different truths. Conflating "not asked" with "asked, awaiting reply"
    # would put a false sentence in the one script whose subject is not saying false things.
    if asked == 0:
        print("  Nothing has been asked yet. The register is honest and empty, which is correct;\n"
              "  it becomes valuable one reply at a time and not one moment sooner.")
    elif answered == 0:
        print("  Letters are out and nothing has come back yet. That is a finding about these\n"
              "  districts, not a gap in the register, and it is publishable as it stands.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mark-asked", metavar="CODE", nargs="+",
                    help="record that we wrote to these districts")
    ap.add_argument("--record", metavar="CODE", help="record a reply from this district")
    ap.add_argument("--date", help="the notified date, verbatim as the officer wrote it")
    ap.add_argument("--none-notified", action="store_true",
                    help="the officer replied that no date is notified")
    ap.add_argument("--reply", help="the officer's own words. Required with --record.")
    ap.add_argument("--on", default=str(date.today()), help="ISO date of the letter or reply")
    args = ap.parse_args()

    doc = _load()

    if args.mark_asked:
        # Resolve every code before writing any of them. A half-applied batch would leave the
        # register claiming we wrote to districts we did not, which is the one thing it must
        # never do — and a typo in the sixth code should not silently commit the first five.
        rows_ = [_row(doc, c) for c in args.mark_asked]
        for r in rows_:
            r["status"], r["asked_on"] = "ASKED", args.on
        _save(doc)
        for r in rows_:
            print(f"  {r['district']}: asked on {args.on}")
        return 0

    if args.record:
        r = _row(doc, args.record)
        if not (args.reply or "").strip():
            print("REFUSED: --reply is required. A date without the officer's words is folklore, "
                  "and this register exists because folklore is what everyone else is publishing.",
                  file=sys.stderr)
            return 1
        if not args.date and not args.none_notified:
            print("REFUSED: give --date or --none-notified.", file=sys.stderr)
            return 1
        if not r["asked_on"]:
            r["asked_on"] = args.on
        r["replied_on"] = args.on
        r["reply_verbatim"] = args.reply.strip()
        if args.none_notified:
            r["status"], r["notified_date"] = "NONE_NOTIFIED", None
        else:
            r["status"], r["notified_date"] = "DATE_NOTIFIED", args.date
        _save(doc)
        print(f"  {r['district']}: {r['status']}"
              + (f" — {r['notified_date']}" if r["notified_date"] else ""))
        return 0

    if not REGISTER.exists():
        _save(doc)
        print(f"  Created {REGISTER.relative_to(ROOT)}\n")
    report(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
