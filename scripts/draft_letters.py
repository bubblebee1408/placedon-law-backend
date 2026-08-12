"""
Render the 31 District Officer letters from one template.

## Why the letter reads the way it does

We are asking a public official, unprompted, to answer a question. Three things follow.

**It must be short.** One question, answerable in one line. Anything longer gets filed.

**It must show we did the work first.** The letter says which sources we already checked and what
they said, so the officer is not being asked to do our research. That is also the honest position:
we are not asking what the law is, we are asking what *this district notified*, which only they
can answer.

**"No date has been notified" must be an explicitly welcome answer.** Otherwise the officer has an
incentive to supply a plausible one, and a plausible-but-invented date is precisely the thing this
register exists to replace. The letter says that outcome is equally useful, because it is.

The letter makes no legal claim. It quotes s.21 and stops.

## What this does not do

It does not send, and it does not touch the register. `asked_on` means *we asked* — a rendered
letter sitting in a folder is not an ask. Mark a district asked only once its letter has actually
gone out:

    python3 scripts/build_register.py --mark-asked IN-KA-BLR --on 2026-08-13

    python3 scripts/draft_letters.py                 # list what would be written
    python3 scripts/draft_letters.py --write         # write .eml files to outbox/
    python3 scripts/draft_letters.py --only IN-KA-BLR --print
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "corpus/reference/notified_dates.json"
OUTBOX = ROOT / "outbox"

SUBJECT = "Query: notified date for the annual report under s.21, PoSH Act 2013 — {district}"

BODY = """\
To
The District Officer, {district}
{state}

Sir / Madam,

Sub: Date notified for submission of the annual report under section 21 of the Sexual
Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013

I am a student in Bengaluru compiling, for public reference, the date each District Officer
in Karnataka has notified for submission of the annual report under section 21 of the above Act.

Section 21(1) provides that the Committee shall in each calendar year prepare an annual report
"in such form and at such time as may be prescribed". Rule 14 of the PoSH Rules, 2013 sets out
the five particulars the report must contain, but I have not been able to find any date
prescribed in the Rules. Most published guidance states 31 January; I have not been able to
trace that date to the Act or the Rules, and I understand at least one District Officer
elsewhere has notified a different date.

I would be grateful if you could tell me, for {district} district:

    Has a date been notified for submission of the annual report, and if so, what is it?

If no date has been notified for this district, that answer is equally useful to me and I would
be glad to record it as such. I do not wish to trouble your office beyond this one question.

Your reply will be recorded and published exactly as you write it, alongside the date of this
letter, and attributed to the office of the District Officer, {district}. If you would prefer
it not be published, please say so and I will keep it unpublished.

Thank you for your time.

Yours faithfully,
{sender}
{sender_email}
"""

SENDER = "Nishant Singh"
SENDER_EMAIL = "nishantsingh14088@gmail.com"


def rows(only: str | None) -> list[dict]:
    if not REGISTER.exists():
        raise SystemExit("REFUSED: register missing. Run scripts/build_register.py first.")
    doc = json.loads(REGISTER.read_text())
    out = [r for r in doc["districts"] if r.get("email")]
    if only:
        out = [r for r in out if r["jurisdiction"] == only]
        if not out:
            raise SystemExit(f"REFUSED: no district with jurisdiction {only!r}.")
    return out


def render(r: dict) -> tuple[str, str]:
    return (SUBJECT.format(district=r["district"]),
            BODY.format(district=r["district"], state=r["state"],
                        sender=SENDER, sender_email=SENDER_EMAIL))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write .eml files to outbox/")
    ap.add_argument("--print", dest="show", action="store_true", help="print the letter")
    ap.add_argument("--only", metavar="CODE", help="one district only")
    ap.add_argument("--batch", type=int, metavar="N", default=None,
                    help="the Nth batch of --size unasked districts (1-based)")
    ap.add_argument("--size", type=int, default=6, help="districts per batch (default 6)")
    args = ap.parse_args()

    rs = rows(args.only)

    # Batching exists for one reason: 29 of the 30 remaining addresses are @gmail.com, and 29
    # near-identical mails from one Gmail account in a single burst is a spam-filter shape. Six
    # a day over a working week keeps the pattern human and gets more of them read. Batches are
    # cut from the UNASKED rows in district order, so re-running after marking a batch asked
    # yields the next six rather than the same six.
    if args.batch is not None:
        unasked = [r for r in rs if r["status"] == "UNASKED"]
        lo = (args.batch - 1) * args.size
        rs = unasked[lo: lo + args.size]
        if not rs:
            raise SystemExit(f"REFUSED: batch {args.batch} is empty — "
                             f"{len(unasked)} district(s) still unasked.")

    if args.show:
        for r in rs:
            subject, body = render(r)
            print(f"To: {r['email']}\nSubject: {subject}\n\n{body}")
        return 0

    if args.write:
        OUTBOX.mkdir(exist_ok=True)
        for r in rs:
            subject, body = render(r)
            m = EmailMessage()
            m["To"], m["From"], m["Subject"] = r["email"], SENDER_EMAIL, subject
            m.set_content(body)
            (OUTBOX / f"{r['jurisdiction']}.eml").write_bytes(bytes(m))
        print(f"  {len(rs)} letters written to {OUTBOX.relative_to(ROOT)}/")
        print("  Open any .eml in a mail client and send, or import the folder.\n")
        print("  The register is UNCHANGED. A drafted letter is not an ask. After sending:")
        print("      python3 scripts/build_register.py --mark-asked <CODE> --on "
              f"{date.today()}")
        return 0

    print(f"  {len(rs)} districts with an email address on file:\n")
    for r in rs:
        print(f"    {r['jurisdiction']:<12} {r['district']:<22} {r['email']:<32} {r['status']}")
    # Counted against the whole register, not against `rs` — `rs` may be a batch or a single
    # district, and subtracting a filtered view from the total reported "25 have no email on
    # file" for a register in which every district has one.
    all_rows = json.loads(REGISTER.read_text())["districts"]
    missing = sum(1 for r in all_rows if not r.get("email"))
    if missing:
        print(f"\n  {missing} district(s) have no email on file and cannot be written to.")
    unasked = sum(1 for r in all_rows if r["status"] == "UNASKED")
    if args.batch is not None:
        print(f"\n  Batch {args.batch} of {-(-unasked // args.size)} remaining "
              f"({unasked} district(s) still unasked).")
    print("\n  --write to render them. Nothing is sent by this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
