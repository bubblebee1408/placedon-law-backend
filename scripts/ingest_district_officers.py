"""
Ingest the District Officer directory from SHe-Box (Ministry of Women & Child Development).

**Why this matters more than it looks.**

s.21/22 require an annual report to the District Officer, and the *date* is fixed by that
officer — not nationally. We have abstained on it since day one, and correctly: Gurugram notified
28 February while most sources repeat 31 January as though it were a rule. Bengaluru's
notification we do not hold.

That abstention was honest but dead-ended. The user was told "we will not guess" and left there.

MWCD publishes the District Officer for every district, publicly, with an official email. So the
abstention can name the person who actually holds the answer:

    "We will not guess your deadline. Your District Officer is Shri. JAGADEESHA G, IAS
     (dcurban@kar.nic.in). Ask them — and tell us what they say, because we will add it."

That converts a refusal into an action. It is also how the corpus grows: every user who asks
their District Officer and reports back closes a gap we cannot close from a laptop.

This is Tier 2 data — a government directory, not statutory text. It never enters the provisions
corpus and is never cited as law. It is contact information, and it is stored separately.

    python3 scripts/ingest_district_officers.py            # Karnataka
    python3 scripts/ingest_district_officers.py --all      # every state
"""
from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "corpus/reference/district_officers.json"

BASE = "https://shebox.wcd.gov.in"
UA = {"X-Requested-With": "XMLHttpRequest",
      "content-type": "application/x-www-form-urlencoded",
      "user-agent": "placedon-hr/0.1 (compliance tool; contact nishantsingh14088@gmail.com)"}


def _ctx() -> ssl.SSLContext:
    """
    A verifying context that actually has roots to verify against.

    This Python reports `ssl.get_default_verify_paths().cafile == None` — the macOS python.org
    installer ships without a CA bundle, so every HTTPS request fails with
    CERTIFICATE_VERIFY_FAILED regardless of the server. curl worked, which is what showed the
    fault was local rather than the site's.

    certifi supplies the roots. Verification stays ON. Disabling it would have "fixed" this in
    one line and quietly turned every future fetch into an unauthenticated one — on a tool whose
    entire value is knowing where its text came from.
    """
    try:
        import certifi                                       # noqa: PLC0415
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _post(path: str, data: dict) -> str:
    req = urllib.request.Request(f"{BASE}/{path}",
                                 data=urllib.parse.urlencode(data).encode(), headers=UA)
    with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:   # noqa: S310
        return r.read().decode("utf-8", errors="replace")


def _deobfuscate(email: str) -> str:
    """MWCD publishes `a[at]b[dot]com` to deter harvesting. Restore it for display."""
    e = email.replace("[at]", "@").replace("[dot]", ".")
    e = re.sub(r"\s+", "", e)
    return e if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) else ""


def states() -> list[dict]:
    return json.loads(_post("getStates", {}))


def officers(state_id: str, stname: str) -> list[dict]:
    body = _post("stateWiseDoDetailsLists", {"state_id": state_id, "stcode": state_id})
    out: list[dict] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        cells = [c for c in cells if c]
        if len(cells) < 5 or cells[0].lower().startswith("s.no"):
            continue
        _, state, district, name, email = cells[:5]
        out.append({
            "state": state.strip(),
            "district": district.strip().title(),
            "officer": name.strip(),
            "email": _deobfuscate(email),
            "email_as_published": email.strip(),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="every state, not just Karnataka")
    args = ap.parse_args()

    try:
        all_states = states()
    except Exception as e:                                   # noqa: BLE001
        print(f"REFUSED: could not reach SHe-Box ({e}). Nothing written.", file=sys.stderr)
        return 1

    wanted = all_states if args.all else [s for s in all_states
                                          if s["stname"].lower() == "karnataka"]
    rows: list[dict] = []
    for s in wanted:
        got = officers(s["id"], s["stname"])
        print(f"  {s['stname']:<28} {len(got):>3} districts")
        rows.extend(got)

    if not rows:
        print("REFUSED: no rows parsed. The page shape changed; fix the parser rather than "
              "writing an empty directory.", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": {
            "name": "SHe-Box District Officer directory",
            "publisher": "Ministry of Women & Child Development, Government of India",
            "url": f"{BASE}/doDetailsLists",
            "fetched_at": str(date.today()),
            "tier": 2,
            "NOT_STATUTORY_TEXT": (
                "A government directory of contact details. It is never cited as law and never "
                "enters the provisions corpus. Its purpose is to make an abstention actionable: "
                "s.21/22 leave the annual-return date to the District Officer, so when we "
                "decline to state a date we can at least name who holds it."
            ),
        },
        "officers": sorted(rows, key=lambda r: (r["state"], r["district"])),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    missing = [r["district"] for r in rows if not r["email"]]
    print(f"\n  {len(rows)} officers -> {OUT.relative_to(ROOT)}")
    if missing:
        print(f"  no usable email for {len(missing)}: {', '.join(missing[:6])}")
    blr = next((r for r in rows if "bengaluru urban" in r["district"].lower()), None)
    if blr:
        print(f"\n  Bengaluru Urban: {blr['officer']} · {blr['email']}")
        print("  This is the officer whose notification sets the annual-return deadline we "
              "currently abstain on (BACKLOG H-3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
