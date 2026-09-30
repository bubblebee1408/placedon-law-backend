"""IBBI public announcements — insolvency, on the counterparty. Ring 2.

## Why this source

PLAN_08 §5 lists IBBI among the registers a counterparty overlay needs, and the
audit in `docs/research/SOURCE_AUDIT_REGISTERS_2026_09_17.md` found it is the ONLY
Indian register of the five checked whose own terms permit reuse. A corporate
debtor entering insolvency is the counterparty fact that bears directly on the
wedge: s.185 loans, s.186 investments, s.188 related-party transactions.

It reports what IBBI published. It decides nothing. An announcement here is a
prompt for a person, never a finding about a company.

## Licence — ATTRIBUTION. The first feed that may be served.

IBBI's own Copyright Policy (`ibbi.gov.in/home/website-policy`, read 2026-09-17,
re-verified 2026-09-18) says, verbatim:

    "Material featured on this site may be reproduced free of charge in any format
    or media without requiring specific permission. This is subject to the material
    being reproduced accurately and not being used in a derogatory manner or in a
    misleading context. Where the material is being published or issued to others,
    the source must be prominently acknowledged. However, the permission to
    reproduce material on this site does not extend to any material which is
    explicitly identified as being the copyright of a third party."

So `LICENCE = ATTRIBUTION`, and unlike `ofac_sdn` and `egazette` this feed's
observations **are** servable commercially -- provided `ATTRIBUTION_TEXT` below is
shown wherever they are. Two conditions bind the wording, not just the credit:
*accurately*, and *not in a misleading context*. Presenting an announcement as
anything other than "IBBI published this on this date" risks the second, which is
why nothing here is summarised, scored or re-labelled.

## What was measured before this was written (2026-09-18)

1. `ibbi.gov.in/robots.txt` is a genuine **404** ("An Internal Error Has
   Occurred"), not a WAF block: RFC 9309 full allowance, the same defined case as
   eGazette and OFAC.
2. `/en/public-announcement` **301s** to `/public-announcement`. The stable entry
   is the redirect target, and both sit on `ibbi.gov.in`.
3. The listing is a real HTML table over plain GET -- no postbacks, no session
   token: 9 columns, 20 data rows per page, `?page=N` for the rest, and the page
   states its own total (**14,835 records** on 2026-09-18).
4. `/claims/corporate-personals` carries only POST **subscription forms** -- email
   alert signups. Those are never automated here: submitting them would create a
   subscription on a government system in someone's name.
5. `/home/downloads` is blank statutory forms, not data.

## Blindness — FLOOR

One page is the newest 20 of ~14,835. The truth is *at least* these announcements.
An absence from this feed is not evidence that a company is not in insolvency.

## The total is a claim, and it is checked

The page states `Total Records -N`. That is the source's own count, and it is
recorded next to the number of rows actually parsed, the same way `ofac_sdn`
records `Record_Count` against its parse. Neither is preferred over the other; a
disagreement is reported.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from checker.feeds import ATTRIBUTION, FLOOR, FetchResult, Observation
from checker.feeds.common.fetch import fetch as _fetch
from checker.robots import HTML
from checker.provenance import ACCESSIBLE

__all__ = ["IbbiAnnouncementsFeed", "Announcement", "parse_listing", "page_url",
           "ENTRY_URL", "HOST", "ATTRIBUTION_TEXT"]

SOURCE_ID = "in.ibbi.public_announcement"
HOST = "ibbi.gov.in"
ENTRY_URL = f"https://{HOST}/public-announcement"
LICENCE = ATTRIBUTION
BLINDNESS = FLOOR

# Required wherever this feed's data is shown. IBBI's terms make the credit a
# condition of the permission, not a courtesy.
ATTRIBUTION_TEXT = ("Source: Insolvency and Bankruptcy Board of India (ibbi.gov.in), "
                    "public announcements. Reproduced under IBBI's Copyright Policy.")

_TOTAL = re.compile(r"Total\s+Records\s*-?\s*([\d,]+)", re.I)
# The header row, read from the live page 2026-09-18. Parsing is positional, so the
# header is verified rather than assumed: a reordered column must fail loudly, not
# silently swap "corporate debtor" with "applicant".
EXPECTED_HEADER = ("s. no.", "type of pa", "date of announcement",
                   "last date of submission", "name of corporate debtor",
                   "name of applicant", "name of insolvency professional",
                   "public announcement", "remarks")


@dataclass(frozen=True)
class Announcement:
    pa_type: str              # "Public Announcement of Corporate Insolvency Resolution Process", etc.
    announced: str            # as written, e.g. "14-09-2026"
    last_submission: str      # claims deadline, as written
    corporate_debtor: str
    applicant: str
    professional: str         # the IP's name; the page also prints their address in this cell
    document_url: str         # the announcement PDF, absolute; "" when the cell has no link
    remarks: str

    @property
    def key(self) -> str:
        """Identity for change detection: the debtor and the date it was announced.

        The table has no id column. The PDF link would be the natural key but is
        absent on some rows, and a row with no link is still an announcement.
        """
        return f"{self.corporate_debtor.strip().casefold()}|{self.announced.strip()}"


def page_url(page: int = 1) -> str:
    if page < 1:
        raise ValueError(f"page numbering starts at 1, got {page}")
    return ENTRY_URL if page == 1 else f"{ENTRY_URL}?page={page}"


def _cells(row_html: str) -> list[str]:
    out = []
    for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S):
        out.append(re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip())
    return out


def _first_pdf(row_html: str) -> str:
    m = re.search(r'href="([^"]+\.pdf)"', row_html, re.I)
    if not m:
        return ""
    href = _html.unescape(m.group(1))
    if href.startswith("http"):
        # The page emits a doubled slash (ibbi.gov.in//uploads/...); harmless to a
        # server, confusing in a record. Normalised in the URL only, never in text.
        return re.sub(r"(?<!:)//+", "/", href.replace("https://", "https:@@")).replace("https:@@", "https://")
    return f"https://{HOST}/{href.lstrip('/')}"


def parse_listing(page: str) -> tuple[list[Announcement], int | None, bool]:
    """`(announcements, total_records_stated, header_matched)`.

    `header_matched` False means the table's own column order is not the one this
    parser was written against. Rows are then NOT returned: a positional parser run
    against a reordered table would quietly swap the corporate debtor with the
    applicant, and a wrong company name is worse than no answer.
    """
    total = None
    m = _TOTAL.search(page)
    if m:
        total = int(m.group(1).replace(",", ""))

    start = page.find("<table")
    if start == -1:
        return [], total, False
    table = page[start:page.find("</table>", start) + 8]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    if not rows:
        return [], total, False

    header = tuple(c.casefold() for c in _cells(rows[0]))
    if header != EXPECTED_HEADER:
        return [], total, False

    out: list[Announcement] = []
    for row in rows[1:]:
        c = _cells(row)
        if len(c) < 9:
            continue                      # a malformed row is dropped, never padded
        out.append(Announcement(
            pa_type=c[1], announced=c[2], last_submission=c[3], corporate_debtor=c[4],
            applicant=c[5], professional=c[6], document_url=_first_pdf(row), remarks=c[8]))
    return out, total, True


class IbbiAnnouncementsFeed:
    """Implements `checker.feeds.Feed`."""

    source_id = SOURCE_ID
    licence = LICENCE

    def __init__(self, *, rules=None, opener=None):
        self._rules = rules
        self._opener = opener

    def fetch(self, entry_url: str = ENTRY_URL) -> FetchResult:
        # FETCH-1: a Drupal public-announcement listing. HTML, declared.
        kw = {"rules": self._rules, "allow_redirect_hosts": (HOST,), "expect": (HTML,)}
        if self._opener is not None:
            kw["opener"] = self._opener
        return _fetch(self.source_id, entry_url, **kw)

    def parse(self, result: FetchResult, *, observed_at: str,
              blindness: str = BLINDNESS) -> Observation:
        if result.source_behaviour != ACCESSIBLE:
            return Observation(source_id=self.source_id, content_sha256=result.sha256,
                               observed_at=observed_at, licence=self.licence,
                               source_behaviour=result.source_behaviour, blindness=blindness)
        items, total, header_ok = parse_listing(
            result.content.decode("utf-8", errors="replace"))
        payload = {
            "attribution": ATTRIBUTION_TEXT,
            "header_matched": header_ok,
            "parsed": len(items),
            "total_records_stated": total,
            "items": [dict(i.__dict__, key=i.key) for i in items],
            "empty_means": "" if items else (
                "the table could not be read as expected (column order changed, or no table "
                "on the page); NOT 'no announcements were published'"),
            "absence_means": "not among the newest announcements listed; NOT 'this company is "
                             "not in insolvency' -- blindness FLOOR, one page of "
                             f"{total if total is not None else 'many'} records",
        }
        return Observation(source_id=self.source_id, content_sha256=result.sha256,
                           observed_at=observed_at, licence=self.licence,
                           source_behaviour=ACCESSIBLE, blindness=blindness, payload=payload)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _test() -> None:
    import os
    import urllib.error
    from email.message import Message

    from checker.feeds import Feed, may_serve_commercially
    from checker.feeds.common.fetch import _FakeResponse
    from checker.robots import parse as parse_robots

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def table(header, *rows):
        h = "<tr>" + "".join(f"<th>{c}</th>" for c in header) + "</tr>"
        body = ""
        for r in rows:
            body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
        return f"<p>Total Records -14835 </p><table>{h}{body}</table>"

    HEADER = ["S. No.", "Type of PA", "Date of Announcement", "Last date of Submission",
              "Name of Corporate Debtor", "Name of Applicant",
              "Name of Insolvency Professional", "Public Announcement", "Remarks"]
    row1 = ["1", "Public Announcement of Corporate Insolvency Resolution Process",
            "14-09-2026", "25-09-2026", "A.NAVINCHANDRA STEELS PRIVATE LIMITED",
            "Abhyudaya Co-operative Bank Limited", "Mr. Anil Vrijdas Rajkotia",
            '<a href="https://ibbi.gov.in//uploads/press/abc.pdf">(1.95 MB)</a>', ""]
    row2 = ["2", "Public Announcement of Voluntary Liquidation", "14-09-2026", "10-10-2026",
            "HUBLI HOTELS PRIVATE LIMITED", "HUBLI HOTELS PRIVATE LIMITED",
            "Mr. Thirupal Gorige", "(2.07 MB)", "note"]
    page = table(HEADER, row1, row2)

    allow_all = parse_robots("")
    deny_all = parse_robots("User-agent: *\nDisallow: /\n")

    def site(body: bytes):
        def opener(url, *, timeout):
            if url.endswith("/en/public-announcement"):
                h = Message(); h["Location"] = ENTRY_URL
                raise urllib.error.HTTPError(url, 301, "Moved", h, None)
            return _FakeResponse(200, body)
        return opener

    feed = IbbiAnnouncementsFeed(rules=allow_all, opener=site(page.encode()))
    check(isinstance(feed, Feed), "IbbiAnnouncementsFeed satisfies the Feed protocol")

    # ---- the licence: this is the first feed that MAY be served ----------------
    servable, why = may_serve_commercially(feed.licence)
    check(servable, f"ATTRIBUTION is servable commercially ({why or 'no restriction'})")
    check("Insolvency and Bankruptcy Board of India" in ATTRIBUTION_TEXT,
          "...and the attribution names the source, as IBBI's terms require")

    r = feed.fetch()
    obs = feed.parse(r, observed_at=_now())
    p = obs.payload
    check(p["attribution"] == ATTRIBUTION_TEXT, "every observation carries the attribution")
    check(p["parsed"] == 2 and p["header_matched"], "both rows parsed against a verified header")
    check(p["total_records_stated"] == 14835, "the page's own total is recorded")
    check(p["items"][0]["corporate_debtor"] == "A.NAVINCHANDRA STEELS PRIVATE LIMITED",
          "the corporate debtor is read from the right column")
    check(p["items"][0]["applicant"] == "Abhyudaya Co-operative Bank Limited",
          "...and the applicant from its own, not confused with the debtor")
    check(p["items"][0]["document_url"] == "https://ibbi.gov.in/uploads/press/abc.pdf",
          f"the doubled slash is normalised in the URL ({p['items'][0]['document_url']})")
    check(p["items"][1]["document_url"] == "", "a row with no link yields no URL, not a guess")
    check(p["items"][0]["key"] != p["items"][1]["key"], "each row has its own identity key")
    check("NOT 'this company is not in insolvency'" in p["absence_means"],
          "the observation says what an absence does NOT mean")
    check(obs.blindness == FLOOR, "blindness FLOOR: one page of ~14,835")

    # ---- a reordered header must refuse, not mis-map ---------------------------
    swapped = HEADER[:]
    swapped[4], swapped[5] = swapped[5], swapped[4]
    items, total, header_ok = parse_listing(table(swapped, row1, row2))
    check(not header_ok and items == [],
          "a reordered column order returns NO rows rather than swapping debtor and applicant")
    check(total == 14835, "...while the stated total is still read")
    bad = IbbiAnnouncementsFeed(rules=allow_all, opener=site(table(swapped, row1).encode()))
    ob2 = bad.parse(bad.fetch(), observed_at=_now())
    check("NOT 'no announcements were published'" in ob2.payload["empty_means"],
          "an unreadable table is not reported as an empty register")

    # ---- failing closed --------------------------------------------------------
    blocked = IbbiAnnouncementsFeed(rules=deny_all, opener=site(page.encode()))
    rb = blocked.fetch()
    check(rb.source_behaviour != ACCESSIBLE and blocked.parse(rb, observed_at=_now()).payload == {},
          "a robots refusal yields no payload")

    def elsewhere(url, *, timeout):
        h = Message(); h["Location"] = "https://evil.example.com/x"
        raise urllib.error.HTTPError(url, 302, "Found", h, None)
    check(IbbiAnnouncementsFeed(rules=allow_all, opener=elsewhere).fetch().source_behaviour
          != ACCESSIBLE, "a redirect off ibbi.gov.in is refused")

    check(page_url(1) == ENTRY_URL and page_url(3).endswith("?page=3"), "pagination URLs")
    try:
        page_url(0); check(False, "page 0 must raise")
    except ValueError:
        check(True, "page 0 raises rather than inventing a page")

    from checker import rings
    check(rings.ring_of("checker.feeds.ibbi") == rings.RING_2, "this module is Ring 2")

    if os.environ.get("THEMIS_LIVE") == "1":
        live = IbbiAnnouncementsFeed()
        lr = live.fetch()
        check(lr.source_behaviour == ACCESSIBLE, f"LIVE: fetched ({lr.note or lr.http_status})")
        if lr.source_behaviour == ACCESSIBLE:
            lp = live.parse(lr, observed_at=_now()).payload
            print(f"         LIVE parsed={lp['parsed']} of {lp['total_records_stated']} stated; "
                  f"header_matched={lp['header_matched']}")
            for it in lp["items"][:3]:
                print(f"           {it['announced']}  {it['corporate_debtor'][:44]:46} {it['pa_type'][:34]}")
            check(lp["header_matched"] and lp["parsed"] > 0,
                  "LIVE: the real table matches the header this parser expects")
    else:
        print("  [SKIP] live fetch (set THEMIS_LIVE=1 to read the real IBBI listing)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
