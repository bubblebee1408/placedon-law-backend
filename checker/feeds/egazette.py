"""The Gazette watcher — the terminal's ticker. Ring 2. Observations only.

## What this is for

D-1: the Companies Act amendment ledger we hold stops at 2023-10-30, and
`corpus_currency.py` measures that gap but, by design, cannot close it — closing it
means acquiring instruments, which is human-attested. What nothing did was *watch*:
notice that the Gazette has published something new, so a person knows to look.

That is this module. It reports what the Gazette has put out; it decides nothing.
A Ministry of Corporate Affairs notification appearing here is a prompt for a human
to acquire and attest it, never an amendment applied to the corpus.

`CLAUDE.md` names the Gazette as a permitted source outright. PLAN_15 §0 calls the
alert that arrives without being asked "the terminal". This is that alert's source.

## What was measured before a line of this was written (2026-09-17)

1. **robots.txt**: a genuine HTTP 404 — RFC 9309 full allowance. (It also timed
   out once; `checker.robots` treats a timeout as closed, which is correct.)

2. **TLS**: egazette.gov.in serves ONLY its leaf certificate. Every verified fetch
   failed until `checker/certs/intermediates.pem` supplied YR2 and Root YR, chaining
   to ISRG Root X1. See that file for the proof the intermediates anchor nothing.

3. **The root 302s to a cookieless-session URL on the same host**:
   `https://egazette.gov.in/(S(<token>))/default.aspx`. So the adapter names
   `egazette.gov.in` as its only redirect host. The token is never stored: a
   `FetchResult` carries the stable entry URL, not the resolved one.

4. **The homepage is the only plain-GET listing.** It carries a "Recent Extra
   Ordinary Gazettes" table and a "Recent Weekly Gazettes" table, each row as spans
   with stable ids (`rpt_Extra_lbl_UGIDExtra_N` and siblings). "View All" and every
   Download control are ASP.NET postbacks (`__doPostBack`); requesting
   `RecentUploads.aspx` directly lands on `error.aspx`. Replaying form state was
   deliberately not done: it is brittle, and it drives the site rather than reading
   it.

5. **The homepage shows only the newest few** (4 extraordinary rows on the day).
   So a poll can miss instruments. That is handled, not hidden — see §Gaps.

6. **PDF address**: Gazette ID `CG-DL-E-17092026-276294` is served at
   `/WriteReadData/2026/276294.pdf` (confirmed with a ranged GET: 206,
   application/pdf). **eGazette answers HEAD with 404 even for files that exist**
   — a HEAD probe would have "disproved" a correct pattern. `CLAUDE.md`: a 404 on a
   URL we constructed is evidence of nothing. This module never probes.

## Gaps — the completeness signal

Gazette IDs are one ascending counter (276294, 276297, 276298, 276299 were listed;
276295 and 276296 were not). Between two polls, every integer above the last one we
saw that no listing showed is reported **UNSEEN** — not "does not exist", not "not
relevant". A number that was published into a category we cannot list, or scrolled
off the homepage between polls, is exactly an UNSEEN number. The watcher names them
so a person can go and look; it does not guess what they are.

Note the counter is shared across State and Central series (`CG-MH-…` appeared
alongside `CG-DL-…`), so an UNSEEN number need not be a Central instrument at all.

## Licence — UNVERIFIED

The site's Disclaimer page renders no text without scripts. Copyright Act 1957
s.52(1)(q) exempts reproducing matter published in the Official Gazette, which is
very likely the basis — but that is our reading of a statute, not the source's own
statement, so `LICENCE_UNVERIFIED` and commercial serving refuses until it is
confirmed. What this feed would serve is metadata and a link, not the document.

## Blindness — FLOOR

The listing is a subset of what was published. The truth is *at least* these
instruments.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from checker.feeds import FLOOR, LICENCE_UNVERIFIED, FetchResult, Observation
from checker.feeds.common.fetch import fetch as _fetch
from checker.robots import HTML
from checker.provenance import ACCESSIBLE

__all__ = ["EGazetteFeed", "GazetteItem", "parse_listing", "watch", "pdf_url",
           "ENTRY_URL", "HOST"]

SOURCE_ID = "in.egazette.recent"
HOST = "egazette.gov.in"
ENTRY_URL = f"https://{HOST}/"
LICENCE = LICENCE_UNVERIFIED
BLINDNESS = FLOOR

CORPORATE_AFFAIRS = "ministry of corporate affairs"
# Weekly gazettes read "This Gazette may contains Multiple Ministries" (sic, the
# site's own wording). Such a row can carry an MCA notification, so the honest
# answer is UNKNOWN, never False -- absence is not denial.
_MULTIPLE = "multiple ministries"

_ID = re.compile(r"^CG-([A-Z]{2})-([EW])-(\d{2})(\d{2})(\d{4})-(\d+)$")

# (repeater prefix, kind, span-id suffix for each column). Read from the live page.
_TABLES = (
    ("rpt_Extra", "EXTRAORDINARY", {"ministry": "MinistryE", "subject": "SubjectE",
                                     "date": "DateE", "gazette_id": "UGIDExtra"}),
    ("rpt_Week", "WEEKLY", None),   # column ids discovered at parse time; see _week_columns
)


@dataclass(frozen=True)
class GazetteItem:
    gazette_id: str
    serial: int            # the trailing counter -- the gap detector's key
    kind: str              # EXTRAORDINARY | WEEKLY
    published: str         # as written on the page, e.g. "17-Sep-2026"
    ministry: str
    subject: str           # the page TRUNCATES this ("..."); never treat it as the text
    pdf_url: str
    corporate_affairs: bool | None   # None = UNKNOWN: the row names no single ministry
    date_agrees: bool | None = None  # RT-12: does the ID's embedded date match the Date column?


def pdf_url(gazette_id: str) -> str:
    """`CG-DL-E-17092026-276294` -> `https://egazette.gov.in/WriteReadData/2026/276294.pdf`.

    Confirmed by GET on 2026-09-17 for one 2025 and one 2026 id. Raises on an id
    that does not have the shape, rather than guessing a year.
    """
    m = _ID.match(gazette_id)
    if not m:
        raise ValueError(f"not a Gazette ID of the shape CG-XX-E-DDMMYYYY-N: {gazette_id!r}")
    year, serial = m.group(5), m.group(6)
    return f"https://{HOST}/WriteReadData/{year}/{serial}.pdf"


_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec")


def _dates_agree(m: "re.Match[str]", published: str) -> bool | None:
    """Does the Gazette ID's embedded DDMMYYYY match the Date column?

    RT-12: the two were never compared, so a mismatch -- a mis-keyed row, or an ID
    reused across days -- would pass silently, and `pdf_url()` derives the YEAR from
    the ID. None means "no date column to compare", not "they agree": an unreadable
    date is not evidence of agreement.
    """
    if not published:
        return None
    parts = published.replace("/", "-").split("-")
    if len(parts) != 3:
        return None
    dd, mon, yyyy = parts[0].strip(), parts[1].strip().lower()[:3], parts[2].strip()
    if mon not in _MONTHS:
        return None
    return (dd.zfill(2), f"{_MONTHS.index(mon) + 1:02d}", yyyy) == (m.group(3), m.group(4), m.group(5))


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


_SPAN_TAG = re.compile(r"<\s*(/?)\s*span\b", re.I)


def _span_body(page: str, start: int) -> str:
    """The text of the span opening at `start`, counting NESTED spans.

    RT-11: the old form was one non-greedy regex to `</span>`, which stops at the
    FIRST close. eGazette wraps values in `<font>` today, but a single nested
    `<span>` -- a styling change on their side, not ours -- would have truncated the
    Ministry cell, and "Ministry of <span>Corporate Affairs</span>" would read as
    "Ministry of": not the MCA string, so the feed's core alert would go quietly
    silent. Depth counting cannot be fooled that way.
    """
    depth, pos = 1, start
    while depth and pos < len(page):
        m = _SPAN_TAG.search(page, pos)
        if not m:
            return page[start:]          # unterminated: take the rest, do not guess
        depth += -1 if m.group(1) else 1
        end = page.find(">", m.end())
        if end == -1:
            return page[start:m.start()]
        pos = end + 1
        if depth == 0:
            return page[start:m.start()]
    return page[start:pos]


def _column(page: str, span_id_prefix: str) -> dict[int, str]:
    pat = re.compile(r'id="' + re.escape(span_id_prefix) + r'_(\d+)"[^>]*>')
    return {int(m.group(1)): _clean(_span_body(page, m.end())) for m in pat.finditer(page)}


def _week_columns(page: str) -> dict[str, str]:
    """The weekly repeater's span suffixes, found rather than assumed: any
    `rpt_Week_lbl_<X>_0` whose value looks like a Gazette ID, a date, or text."""
    found = set(re.findall(r'id="rpt_Week_lbl_([A-Za-z]+)_0"', page))
    cols: dict[str, str] = {}
    for suffix in found:
        v = _column(page, f"rpt_Week_lbl_{suffix}").get(0, "")
        if _ID.match(v):
            cols["gazette_id"] = suffix
        elif re.match(r"^\d{2}-[A-Za-z]{3}-\d{4}$", v):
            cols["date"] = suffix
        elif suffix.lower().startswith("ministr"):
            cols["ministry"] = suffix
        elif suffix.lower().startswith("subject"):
            cols["subject"] = suffix
    return cols


def parse_listing(page: str) -> list[GazetteItem]:
    """Every Gazette row the homepage shows, newest first by serial.

    A row whose id is not a well-formed Gazette ID is DROPPED, not repaired -- the
    same rule `checker/document_extract.py` applies to a damaged CIN.
    """
    items: dict[str, GazetteItem] = {}
    for prefix, kind, cols in _TABLES:
        cols = cols or _week_columns(page)
        if "gazette_id" not in cols:
            continue
        ids = _column(page, f"{prefix}_lbl_{cols['gazette_id']}")
        get = {k: _column(page, f"{prefix}_lbl_{v}") for k, v in cols.items() if k != "gazette_id"}
        for n, gid in ids.items():
            m = _ID.match(gid)
            if not m:
                continue
            ministry = get.get("ministry", {}).get(n, "")
            published = get.get("date", {}).get(n, "")
            items[gid] = GazetteItem(
                gazette_id=gid, serial=int(m.group(6)), kind=kind,
                published=get.get("date", {}).get(n, ""),
                ministry=ministry, subject=get.get("subject", {}).get(n, ""),
                pdf_url=pdf_url(gid),
                date_agrees=_dates_agree(m, published),
                corporate_affairs=(None if (not ministry or _MULTIPLE in ministry.casefold())
                                   else CORPORATE_AFFAIRS in ministry.casefold()),
            )
    return sorted(items.values(), key=lambda i: i.serial, reverse=True)


def watch(items: list[GazetteItem], last_seen_serial: int | None) -> dict:
    """What is new since `last_seen_serial`, and which serials no listing showed.

    First run (`last_seen_serial=None`) reports everything listed as new and names
    no gaps -- there is no baseline to have a gap against, and inventing one would
    be the interpolation `CLAUDE.md` forbids.
    """
    serials = sorted({i.serial for i in items})
    new = [i for i in items if last_seen_serial is None or i.serial > last_seen_serial]
    unseen: list[int] = []
    if last_seen_serial is not None and serials:
        top = serials[-1]
        listed = set(serials)
        unseen = [s for s in range(last_seen_serial + 1, top + 1) if s not in listed]
    return {
        "new": new,
        "new_corporate_affairs": [i for i in new if i.corporate_affairs is True],
        "new_ministry_unknown": [i for i in new if i.corporate_affairs is None],
        "unseen_serials": unseen,
        "unseen_means": "published under a counter value no plain-GET listing showed -- "
                        "possibly another series or category, possibly scrolled off. NOT "
                        "'does not exist'. A person should look.",
        "high_water": max(serials) if serials else last_seen_serial,
    }


class EGazetteFeed:
    """Implements `checker.feeds.Feed`."""

    source_id = SOURCE_ID
    licence = LICENCE

    def __init__(self, *, rules=None, opener=None):
        self._rules = rules
        self._opener = opener

    def fetch(self, entry_url: str = ENTRY_URL) -> FetchResult:
        # FETCH-1: this source IS a web listing, so HTML is what it legitimately
        # expects and it says so. Declaring it is what lets every other adapter
        # refuse a page -- a default that accepted anything would protect nobody.
        kw = {"rules": self._rules, "allow_redirect_hosts": (HOST,), "expect": (HTML,)}
        if self._opener is not None:
            kw["opener"] = self._opener
        return _fetch(self.source_id, entry_url, **kw)

    def parse(self, result: FetchResult, *, observed_at: str,
              blindness: str = BLINDNESS, last_seen_serial: int | None = None) -> Observation:
        if result.source_behaviour != ACCESSIBLE:
            return Observation(source_id=self.source_id, content_sha256=result.sha256,
                               observed_at=observed_at, licence=self.licence,
                               source_behaviour=result.source_behaviour, blindness=blindness)
        page = result.content.decode("utf-8", errors="replace")
        items = parse_listing(page)
        w = watch(items, last_seen_serial)
        payload = {
            "listed": len(items),
            # A page that answered 200 but lists nothing is not "the Gazette published
            # nothing" -- it is a page we could not read. Said explicitly.
            "listing_empty_means": "the page could not be read as a listing; NOT "
                                   "'nothing was published'" if not items else "",
            "items": [i.__dict__ for i in items],
            "new_serials": [i.serial for i in w["new"]],
            "new_corporate_affairs": [i.gazette_id for i in w["new_corporate_affairs"]],
            # Weekly and other multi-ministry gazettes: MAY hold an MCA item. Not a no.
            "new_ministry_unknown": [i.gazette_id for i in w["new_ministry_unknown"]],
            "unseen_serials": w["unseen_serials"],
            "unseen_means": w["unseen_means"],
            "high_water": w["high_water"],
            "subject_is_truncated": True,
            # RT-12: rows whose ID date and Date column disagree. Reported, never
            # repaired -- which of the two is right is not ours to decide.
            "date_mismatch": [i.gazette_id for i in items if i.date_agrees is False],
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

    def row(prefix, n, cols, vals):
        return "".join(f'<span id="{prefix}_lbl_{c}_{n}"><font size="2">{v}</font></span>'
                       for c, v in zip(cols, vals))

    ex = ["MinistryE", "SubjectE", "DateE", "UGIDExtra"]
    # The weekly repeater's REAL span suffixes, read from the live page 2026-09-17,
    # including FileSizeW, which the column detector must ignore.
    wk = ["MinistryW", "SubjectW", "DateW", "UGIDWeekly", "FileSizeW"]
    page = ("<html>Recent Extra Ordinary Gazettes"
            + row("rpt_Extra", 0, ex, ["Ministry of Labour and Employment", "In exercise of...",
                                        "17-Sep-2026", "CG-DL-E-17092026-276299"])
            + row("rpt_Extra", 1, ex, ["Ministry of Corporate Affairs", "In exercise of the powers...",
                                        "17-Sep-2026", "CG-DL-E-17092026-276298"])
            + row("rpt_Extra", 2, ex, ["PMO --&gt; Department of Atomic Energy", "...",
                                        "17-Sep-2026", "CG-MH-E-17092026-276297"])
            + row("rpt_Extra", 3, ex, ["Somebody", "...", "17-Sep-2026", "NOT-A-GAZETTE-ID"])
            + "Recent Weekly Gazettes"
            + row("rpt_Week", 0, wk, ["This Gazette may contains Multiple Ministries",
                                       "This Gazette may contains Multiple Subjects",
                                       "13-Sep-2026", "CG-DL-W-13092026-276290", "0.88 MB"])
            + "</html>")

    allow_all = parse_robots("")
    deny_all = parse_robots("User-agent: *\nDisallow: /\n")

    def site(body: bytes):
        """The measured behaviour: root 302s to a cookieless-session URL, same host."""
        def opener(url, *, timeout):
            if url == ENTRY_URL:
                h = Message(); h["Location"] = f"https://{HOST}/(S(abc123token))/default.aspx"
                raise urllib.error.HTTPError(url, 302, "Found", h, None)
            return _FakeResponse(200, body)
        return opener

    feed = EGazetteFeed(rules=allow_all, opener=site(page.encode()))
    check(isinstance(feed, Feed), "EGazetteFeed satisfies the Feed protocol")
    check(not may_serve_commercially(feed.licence)[0], "licence UNVERIFIED -> refuses commercial serving")

    r = feed.fetch()
    check(r.source_behaviour == ACCESSIBLE, "the same-host session redirect is followed")
    check(r.url == ENTRY_URL and "(S(" not in r.url, "the session token is never the stored identity")

    # ---- FETCH-1: HTML is what this source legitimately IS ------------------
    # This adapter declares expect=(HTML,), so a 200 of HTML is still evidence here --
    # correctly, because the source is a web listing. What the declaration buys is that
    # the payload guard now refuses a non-page: a PDF or other binary arriving where the
    # listing was expected used to reach parse_listing(), which would find no rows and
    # report a quiet day. It is also what lets every OTHER adapter refuse a page, since
    # the guard has no permissive default to fall back on.
    pdf = _FakeResponse(200, b"%PDF-1.7\n%\xe2\xe3\xcf\xd3 370 pages of the Act",
                        headers={"Content-Type": "application/pdf"})
    r_pdf = EGazetteFeed(rules=allow_all,
                         opener=lambda url, *, timeout: pdf).fetch()
    check(r_pdf.source_behaviour != ACCESSIBLE and not r_pdf.content,
          "a PDF where the gazette LISTING was expected is refused, not parsed for rows")
    check("HTML" in r_pdf.note and "application/pdf" in r_pdf.note,
          f"...and the note names both sides of the mismatch ({r_pdf.note})")

    # ---- parsing ----
    items = parse_listing(page)
    check(len(items) == 4, f"four well-formed rows parsed across both tables (got {len(items)})")
    check(all(i.gazette_id != "NOT-A-GAZETTE-ID" for i in items), "a malformed id is dropped, not repaired")
    check([i.serial for i in items] == [276299, 276298, 276297, 276290], "newest first by serial")
    check({i.kind for i in items} == {"EXTRAORDINARY", "WEEKLY"}, "both tables are read")
    check(next(i for i in items if i.serial == 276297).ministry == "PMO --> Department of Atomic Energy",
          "HTML entities are decoded")
    mca = [i for i in items if i.corporate_affairs is True]
    check(len(mca) == 1 and mca[0].serial == 276298, "the Corporate Affairs instrument is flagged")
    wk_item = next(i for i in items if i.kind == "WEEKLY")
    check(wk_item.corporate_affairs is None,
          "a multi-ministry weekly is UNKNOWN for Corporate Affairs, never a false no")
    check(next(i for i in items if i.serial == 276299).corporate_affairs is False,
          "a single named non-MCA ministry is a genuine no")
    check(pdf_url("CG-DL-E-17092026-276294") == "https://egazette.gov.in/WriteReadData/2026/276294.pdf",
          "id -> PDF address, as confirmed live")
    try:
        pdf_url("CG-DL-E-276294"); check(False, "a malformed id must raise")
    except ValueError:
        check(True, "a malformed id raises rather than guessing a year")

    # ---- RT-11: a nested span must not truncate the Ministry cell ----
    nested = ('<span id="rpt_Extra_lbl_MinistryE_0">Ministry of <span style="x">Corporate '
              'Affairs</span></span>'
              '<span id="rpt_Extra_lbl_SubjectE_0">...</span>'
              '<span id="rpt_Extra_lbl_DateE_0">18-Sep-2026</span>'
              '<span id="rpt_Extra_lbl_UGIDExtra_0">CG-DL-E-18092026-300</span>')
    ni = parse_listing(nested)
    check(len(ni) == 1 and ni[0].ministry == "Ministry of Corporate Affairs",
          f"a nested span keeps the whole ministry name (got {ni[0].ministry!r})")
    check(ni[0].corporate_affairs is True,
          "...so the MCA alert still fires -- RT-11 would have silenced it")

    # ---- RT-12: the ID's own date against the Date column --------------------
    good = next(i for i in items if i.serial == 276299)
    check(good.date_agrees is True, "a row whose ID date matches its Date column agrees")
    mism = ('<span id="rpt_Extra_lbl_MinistryE_0">Ministry of Labour</span>'
            '<span id="rpt_Extra_lbl_SubjectE_0">...</span>'
            '<span id="rpt_Extra_lbl_DateE_0">11-Sep-2026</span>'
            '<span id="rpt_Extra_lbl_UGIDExtra_0">CG-DL-E-17092026-301</span>')
    mi = parse_listing(mism)
    check(mi[0].date_agrees is False, "a row whose ID date contradicts its Date column is flagged")
    nodate = mism.replace('<span id="rpt_Extra_lbl_DateE_0">11-Sep-2026</span>', "")
    check(parse_listing(nodate)[0].date_agrees is None,
          "no readable date is UNKNOWN, not agreement")

    # ---- watching ----
    first = watch(items, None)
    check(len(first["new"]) == 4 and first["unseen_serials"] == [],
          "first run: everything is new, and NO gaps are invented without a baseline")
    later = watch(items, 276293)
    check([i.serial for i in later["new"]] == [276299, 276298, 276297],
          "only serials above the high-water mark are new")
    check(later["unseen_serials"] == [276294, 276295, 276296],
          f"serials no listing showed are named UNSEEN ({later['unseen_serials']})")
    check("NOT 'does not exist'" in later["unseen_means"], "...and UNSEEN says what it does not mean")
    check(later["high_water"] == 276299, "the new high-water mark is the highest listed serial")
    quiet = watch(items, 276299)
    check(quiet["new"] == [] and quiet["unseen_serials"] == [], "no change -> nothing new, no gaps")

    obs = feed.parse(r, observed_at=_now(), last_seen_serial=276293)
    p = obs.payload
    check(obs.blindness == FLOOR, "blindness FLOOR: the listing is a subset of what was published")
    check(p["new_corporate_affairs"] == ["CG-DL-E-17092026-276298"], "the observation surfaces the MCA item")
    check(p["new_ministry_unknown"] == [], "no weekly above the high-water mark here")
    check(watch(items, 276000)["new_ministry_unknown"][0].kind == "WEEKLY",
          "a new weekly is surfaced as ministry-UNKNOWN for a person to open")
    check(p["subject_is_truncated"] is True, "the observation says the subject is truncated")

    # ---- failing closed ----
    blank = EGazetteFeed(rules=allow_all, opener=site(b"<html>error</html>"))
    ob = blank.parse(blank.fetch(), observed_at=_now())
    check(ob.payload["listed"] == 0 and "NOT 'nothing was published'" in ob.payload["listing_empty_means"],
          "an unreadable page is NOT reported as 'nothing was published'")
    blocked = EGazetteFeed(rules=deny_all, opener=site(page.encode()))
    rb = blocked.fetch()
    check(rb.source_behaviour != ACCESSIBLE and blocked.parse(rb, observed_at=_now()).payload == {},
          "a robots refusal yields no payload")

    def elsewhere(url, *, timeout):
        h = Message(); h["Location"] = "https://evil.example.com/default.aspx"
        raise urllib.error.HTTPError(url, 302, "Found", h, None)
    check(EGazetteFeed(rules=allow_all, opener=elsewhere).fetch().source_behaviour != ACCESSIBLE,
          "a redirect off egazette.gov.in is refused")

    from checker import rings
    check(rings.ring_of("checker.feeds.egazette") == rings.RING_2, "this module is Ring 2")

    if os.environ.get("THEMIS_LIVE") == "1":
        live = EGazetteFeed()
        lr = live.fetch()
        check(lr.source_behaviour == ACCESSIBLE, f"LIVE: fetched ({lr.note or lr.http_status})")
        if lr.source_behaviour == ACCESSIBLE:
            lp = live.parse(lr, observed_at=_now()).payload
            print(f"         LIVE listed={lp['listed']} high_water={lp['high_water']} "
                  f"MCA={lp['new_corporate_affairs']} ministry_unknown={lp['new_ministry_unknown']}")
            for it in lp["items"]:
                print(f"           {it['published']}  {it['gazette_id']:28} {it['kind']:13} {it['ministry'][:48]}")
            check(lp["listed"] > 0, "LIVE: the homepage parses into at least one Gazette row")
    else:
        print("  [SKIP] live fetch (set THEMIS_LIVE=1 to read the real eGazette homepage)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
