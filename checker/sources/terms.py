"""What each Indian source actually permits — read from the source, never from memory.

S0 of `docs/plans/PLAN_26_INDIAN_SOURCES.md` §5. One
record per source: the terms URL, the date it was read, the exact clauses that govern
caching, attribution, commercial use and rate limits, and the robots.txt result for every
path a connector intends to fetch.

## The one rule that makes this file worth having

**An unread term is OPEN.** Not "probably fine", not the gist of what a search result said,
not what the plan document wrote down before anyone fetched anything. A clause is `READ`
only when this repository fetched the page and the words below are that page's words. Every
quote here was extracted from a saved response body by a script, not typed from memory.

That rule cost the plan its own numbers. `docs/plans/PLAN_26_INDIAN_SOURCES.md` §3 recorded
Indian Kanoon at "search ~ ₹5 per 100 results; full text +₹0.20 per record" and GODL as
"commercial and non-commercial use permitted with attribution", both from search-result
summaries. The pricing page says ₹0.50 per search (see `_IK_PRICING`), and the GODL page
**could not be fetched at all** (see `data_gov_in`). The plan said so — "read from search
results only ... the laptop session must fetch and quote each one itself" — and this is that
session. Where the two disagree, this file is what was measured.

## Everything here went through checker/robots.py

Not alongside it. `fetch_rules()` decided whether each page could be read, `Fetcher.get()`
read it, and `payload_refusal()` checked that what came back was the kind of thing asked
for. Where robots.txt refused, the page is unread and its clauses are OPEN — there is no
second path in this module, and a blocked source is recorded as blocked (CLAUDE.md: "Do not
bypass the MCA WAF, robots restrictions, access controls, or source terms").

Reading `/robots.txt` itself is the one request that needs no permission, so a refusal
*of that file* is recorded verbatim as the evidence of the refusal.

## What was found, in one paragraph

Two of the seven sources are flatly closed: `www.data.gov.in` and `www.bseindia.com` both
answer `/robots.txt` with an HTTP 403 "Access Denied", and the data.gov.in apex — which does
answer — publishes `User-agent: *` / `Disallow: /`, so **the MCA open-data route S2 depends on
is shut by robots, not merely awkward**. RBI answers `/robots.txt` with an HTTP 418 WAF page
(which is why `checker/robots.py` now treats 418 as a refusal) and its disclaimer separately
**prohibits caching in terms**. NSE permits us by robots and then drops the connection on
every policy page, so its terms are unread. e-Gazette publishes no robots.txt (a genuine 404,
so allowed) but 500s on its policy pages. Only **Indian Kanoon** and **SEBI** have terms that
were actually read — and neither of them says anything at all about caching.

Consequently `may_cache()` is False for all seven of those scraped web sources. That is not a
bug in this file; it is the answer.

Two further sources were added 2026-10-05: the AWS Open Data eCourts judgment datasets
(Supreme Court and High Court), owner-approved, managed by Dattam Labs, licensed CC-BY-4.0.
Their terms are a standard open-data LICENCE rather than a scraped policy page, so for them
`may_cache()` is True — CC-BY grants redistribution. They are the two exceptions to the
paragraph above, and the only cacheable sources in the file.

Run: PYTHONPATH=. python3 checker/sources/terms.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── clause topics: the four the job named, and no more ───────────────────────
CACHING = "CACHING"
ATTRIBUTION = "ATTRIBUTION"
COMMERCIAL_USE = "COMMERCIAL_USE"
RATE_LIMIT = "RATE_LIMIT"
TOPICS = (CACHING, ATTRIBUTION, COMMERCIAL_USE, RATE_LIMIT)

# ── what we know about a clause ──────────────────────────────────────────────
READ = "READ"                  # fetched, and the quote is the page's own words
OPEN = "OPEN"                  # NOT read. Never an inference, never a summary
PROHIBITED = "PROHIBITED"      # read, and it says no
PERMISSION_REQUIRED = "PERMISSION_REQUIRED"   # read, and it says yes only after asking
CLAUSE_STATES = (READ, OPEN, PROHIBITED, PERMISSION_REQUIRED)

# Only these let a connector act without asking a human first. PERMISSION_REQUIRED is
# deliberately NOT here: "you may, after emailing us" is a permission we have not got.
PERMISSIVE = (READ,)

# ── what happened when we asked for robots.txt ───────────────────────────────
# Same vocabulary as checker/provenance.py, so the two files describe the world the
# same way: a 403 and a timeout are not the same fact about a source.
ACCESSIBLE = "ACCESSIBLE"      # served a robots.txt we could parse
NOT_FOUND = "NOT_FOUND"        # answered 404/410: no rules published, allowance (RFC 9309)
BLOCKED = "BLOCKED"            # 401/403/407/418/429: a refusal. Never worked around
UNREACHABLE = "UNREACHABLE"    # never answered: DNS, refused connection, timeout
ROBOTS_STATES = (ACCESSIBLE, NOT_FOUND, BLOCKED, UNREACHABLE)
ROBOTS_PERMISSIVE = (ACCESSIBLE, NOT_FOUND)


class NoTermsRecord(LookupError):
    """Raised when a connector asks for a source this file does not hold.

    A LookupError and not a warning: PLAN_26 §3 says "a connector refuses to load without
    its record", and a warning is a thing a caller can ignore.
    """


@dataclass(frozen=True)
class Clause:
    """One governed topic, and the source's own words about it.

    The invariant enforced below is the whole point of the class: a clause that claims to
    have been READ must carry the words it was read from, and a clause that is OPEN must
    carry none. Without it, "OPEN" would be a place to park a paraphrase.
    """
    topic: str
    state: str
    quote: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.topic not in TOPICS:
            raise ValueError(f"{self.topic!r} is not one of {TOPICS}")
        if self.state not in CLAUSE_STATES:
            raise ValueError(f"{self.state!r} is not one of {CLAUSE_STATES}")
        if self.state == OPEN and self.quote:
            raise ValueError(
                f"{self.topic} is OPEN but carries a quote -- an unread term has no words. "
                f"If the page was read, the state is not OPEN")
        if self.state != OPEN and not self.quote.strip():
            raise ValueError(
                f"{self.topic} is {self.state} with no quote -- a term we claim to have "
                f"read must say what it says")

    @property
    def permits(self) -> bool:
        return self.state in PERMISSIVE


@dataclass(frozen=True)
class RobotsResult:
    """One origin's robots.txt, as served, with the intended paths decided against it."""
    origin: str
    state: str
    http: int                       # the status, or -1 when nothing answered
    loaded: bool                    # checker.robots.Rules.loaded, verbatim
    verbatim: str                   # the body as served: the rules, or the refusal page
    disallow_count: int = 0
    crawl_delay: float | None = None
    effective_delay: float = 2.0    # our courtesy floor, or theirs if slower
    paths: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in ROBOTS_STATES:
            raise ValueError(f"{self.state!r} is not one of {ROBOTS_STATES}")
        # A refusal that carries no evidence of itself is an assertion. The 403/418 bodies
        # are short and they are the proof, so they are stored.
        if self.state in (BLOCKED,) and not self.verbatim.strip():
            raise ValueError(f"{self.origin} is BLOCKED with no response recorded")

    @property
    def permits(self) -> bool:
        return self.state in ROBOTS_PERMISSIVE and self.loaded


@dataclass(frozen=True)
class TermsRecord:
    source_id: str
    name: str
    terms_url: str                  # "" when no terms page could be read
    date_read: str                  # ISO date, or "" when nothing was read
    clauses: tuple[Clause, ...]
    robots: tuple[RobotsResult, ...]
    note: str = ""

    def __post_init__(self) -> None:
        have = {c.topic for c in self.clauses}
        if have != set(TOPICS):
            raise ValueError(
                f"{self.source_id}: a record must state all four topics (missing "
                f"{sorted(set(TOPICS) - have)}); an omitted topic reads as 'fine'")
        if not self.robots:
            raise ValueError(f"{self.source_id}: a record must carry a robots result")
        if self.terms_url and not self.date_read:
            raise ValueError(f"{self.source_id}: a terms page was read with no date")

    def clause(self, topic: str) -> Clause:
        for c in self.clauses:
            if c.topic == topic:
                return c
        raise ValueError(f"{topic!r} is not one of {TOPICS}")


# ── the exact words, extracted from saved response bodies by script ──────────
#
# Each quote below was pulled out of the stored body with a regex, printed, and pasted.
# Nothing here was typed from memory, which is the only way the "unread is OPEN" rule
# means anything.

_IK_ATTRIBUTION = (
    "Whenever you use IKanoon's search results, documents, or any of our document "
    "classifiers to show information to users—whether directly, for building context "
    "for a Retrieval-Augmented Generation (RAG) system, or for fine-tuning Large/Small "
    "Language Models—you must provide clear and conspicuous attribution. This is a "
    "requirement for using our \"API Services.\" To fulfill this requirement, you must "
    "show the 'powered by IKanoon' logo as shown in the table below. The placement of "
    "this graphic should be appropriate to the specific use case:"
)
_IK_PRICING = (
    "Search 0.50 / Original Document 0.50 / Document 0.20 / Document Fragment 0.05 / "
    "Document Metainfo 0.02 [INR per request]. You would get free Rs 500 to develop and "
    "test your API integration. You would get that as soon as you sign up for the API "
    "services. Non-commercial use case will get free Rs. 10,000 every month but will "
    "require use-case verification by the site administrator."
)
_IK_PREPAID = (
    "You understand that the service is available on a pre-paid mode, i.e., if your "
    "balance runs out then the \"API service\" will not return any result."
)
_SEBI_REPRODUCTION = (
    "Material featured on this Website may be reproduced free of charge after taking "
    "proper permission by sending a mail to us. However, the material has to be "
    "reproduced accurately and not to be used in a derogatory manner or in a misleading "
    "context. Wherever the material is being published or issued to others, the source "
    "must be prominently acknowledged. However, the permission to reproduce this material "
    "shall not extend to any material which is identified as being copyright of a third "
    "party. Authorisation to reproduce such material must be obtained from respective "
    "copyright holders concerned."
)
_SEBI_NOT_LAW = (
    "Though all efforts have been made to ensure the accuracy and currency of the content "
    "on this Website, the same should not be construed as a statement of law or used for "
    "any legal purposes."
)
_RBI_CACHING = (
    "Except as set forth below, caching and links to, and the framing of this Web Site or "
    "any of the contents are prohibited."
)
_RBI_DEEP_LINK = (
    "For hyper-Linking to an internal page of this Web Site (not being the Home Page) the "
    "user must make a specific request for, and secure permission from RBI prior to "
    "hyper-linking to, or framing, this Web Site or any of the contents, or engaging in "
    "similar activities."
)

_ACCESS_DENIED = (
    "<HTML><HEAD> <TITLE>Access Denied</TITLE> </HEAD><BODY> <H1>Access Denied</H1>  "
    "You don't have permission to access \"http://www.{host}/robots.txt\" on this server."
)
_RBI_418 = (
    "<html><head><title>Unauthorised Access </title>...</head><body>You are not "
    "authorized to view this page. Please contact concerned Support Team. "
    "Support ID: 679480896998159213</body></html>"
)

READ_ON = "2026-09-30"          # every fetch in this file, one session, IST evening
READ_AWS = "2026-10-05"         # the AWS Open Data judgment datasets, a later session

# CC-BY-4.0, from the licence deed at https://creativecommons.org/licenses/by/4.0/ (fetched
# 2026-10-05). The deed's words, not the 7391-word legal code: these are what the deed shows
# a reuser, and they are the same for every CC-BY-4.0 work. The party to credit for THESE
# datasets (Dattam Labs, from eCourts) comes from the AWS Open Data Registry YAML, recorded in
# each record's note -- the licence states the REQUIREMENT, the registry states the PARTY.
_CCBY_ATTRIBUTION = (
    "You must give appropriate credit, provide a link to the license, and indicate if "
    "changes were made. You may do so in any reasonable manner, but not in any way that "
    "suggests the licensor endorses you or your use."
)
_CCBY_SHARE = (
    "Share — copy and redistribute the material in any medium or format"
)
_CCBY_COMMERCIAL = (
    "Adapt — remix, transform, and build upon the material for any purpose, even "
    "commercially."
)
# The bucket's own virtual host answers /robots.txt with S3's NoSuchKey, a genuine 404 that
# RFC 9309 and checker/robots.py read as allowance. NOT Amazon's shared s3.ap-south-1 service
# root, which 403s a keyless request generically for every bucket -- that 403 is not a crawl
# directive about THIS dataset, and recording it would falsely mark an owner-approved,
# CC-BY-4.0, registry-published open dataset as refused.
_S3_NOSUCHKEY = (
    "<?xml version=\"1.0\"?><Error><Code>NoSuchKey</Code><Message>The specified key does "
    "not exist.</Message><Key>robots.txt</Key></Error> (S3 REST, application/xml, HTTP 404)"
)

# ── the register ─────────────────────────────────────────────────────────────

RECORDS: tuple[TermsRecord, ...] = (
    TermsRecord(
        source_id="indiankanoon",
        name="Indian Kanoon API",
        terms_url="https://api.indiankanoon.org/terms/",
        date_read=READ_ON,
        clauses=(
            Clause(ATTRIBUTION, READ, _IK_ATTRIBUTION,
                   "The strictest attribution clause of the nine, and it names our exact "
                   "use: RAG context counts, not only display. It requires the LOGO, not "
                   "the words -- PLAN_26 §2 says the label is 'Powered by IKanoon', which "
                   "is the text and not what this clause asks for. A text-only credit does "
                   "not satisfy it."),
            Clause(COMMERCIAL_USE, READ, _IK_PRICING + " " + _IK_PREPAID,
                   "Commercial use is permitted on paid terms. The plan's figures were "
                   "wrong: search is Rs 0.50 per request, not ~Rs 5 per 100 results."),
            Clause(RATE_LIMIT, OPEN,
                   note="The terms name no rate limit; the prepaid balance is the only "
                        "limiter they describe. Absence of a clause is not permission to "
                        "hammer it, so our own floor applies: robots.txt publishes no "
                        "Crawl-delay, so checker.robots.DEFAULT_DELAY_S (2s) governs."),
            Clause(CACHING, OPEN,
                   note="Read the whole terms page and it does not address whether WE may "
                        "store what we fetch. The only occurrence of the word is about "
                        "IKanoon's own caching causing result differences, which is not a "
                        "grant. DECISION_harvey_parity's reversal condition turns on this "
                        "exact question, so it must be asked, not assumed: until then S3 "
                        "quotes at request time and stores nothing."),
        ),
        robots=(
            RobotsResult(
                origin="https://api.indiankanoon.org", state=ACCESSIBLE, http=200,
                loaded=True,
                verbatim="User-agent: * / Disallow: /cached/ / Disallow: /change_device/ "
                         "/ Disallow: /doc/1987695/ ... (9292 Disallow rules)",
                disallow_count=9292, crawl_delay=None, effective_delay=2.0,
                paths={"https://api.indiankanoon.org/search/": True,
                       "https://api.indiankanoon.org/doc/123456/": True,
                       "https://api.indiankanoon.org/docfragment/123456/": True,
                       "https://api.indiankanoon.org/origdoc/123456/": True,
                       "https://api.indiankanoon.org/docmeta/123456/": True}),
            RobotsResult(
                origin="https://indiankanoon.org", state=ACCESSIBLE, http=200, loaded=True,
                verbatim="the same 9292-rule denylist as the API origin",
                disallow_count=9292, crawl_delay=None, effective_delay=2.0,
                paths={"https://indiankanoon.org/doc/123456/": True,
                       "https://indiankanoon.org/search/": True}),
        ),
        note="The 9,292 Disallow lines are individually named documents -- almost certainly "
             "delisting requests from the people those judgments concern. checker/robots.py "
             "was written for this file and enforces it per URL. A `/doc/<id>/` that is "
             "allowed today can be denied tomorrow, so the ruleset is re-read, never "
             "cached as a list.",
    ),

    TermsRecord(
        source_id="sebi",
        name="SEBI (Securities and Exchange Board of India)",
        terms_url="https://www.sebi.gov.in/website-policy.html",
        date_read=READ_ON,
        clauses=(
            Clause(ATTRIBUTION, READ, _SEBI_REPRODUCTION,
                   "Same clause covers attribution and reproduction: the source 'must be "
                   "prominently acknowledged'."),
            Clause(COMMERCIAL_USE, PERMISSION_REQUIRED, _SEBI_REPRODUCTION,
                   "'free of charge AFTER taking proper permission by sending a mail to "
                   "us' -- free, and gated. We have not sent that mail, so we do not have "
                   "the permission; PERMISSION_REQUIRED is not in PERMISSIVE for that "
                   "reason."),
            Clause(RATE_LIMIT, OPEN,
                   note="No rate clause in the policy. robots.txt publishes no "
                        "Crawl-delay, so our 2s floor governs."),
            Clause(CACHING, OPEN,
                   note="Not addressed. Storing a fetched circular is arguably the "
                        "'reproduction' the copyright clause gates on permission, which "
                        "is a reading and not a quote -- so it stays OPEN and the owner "
                        "asks."),
        ),
        robots=(
            RobotsResult(
                origin="https://www.sebi.gov.in", state=ACCESSIBLE, http=200, loaded=True,
                verbatim="User-agent: *\nDisallow: \nDisallow: /js\nDisallow: /hindi/js\n"
                         "Disallow: /css\nDisallow: /hindi/css",
                disallow_count=4, crawl_delay=None, effective_delay=2.0,
                paths={"https://www.sebi.gov.in/legal/circulars": True,
                       "https://www.sebi.gov.in/sebiweb/home/HomeAction.do": True}),
        ),
        note="SEBI's own policy says its content 'should not be construed as a statement of "
             "law or used for any legal purposes': " + _SEBI_NOT_LAW + " The tier rule in "
             "PLAN_26 §2 -- that only HELD may make an answer VERIFIED -- is what the "
             "publisher itself asks for here. Four other candidate policy URLs "
             "(terms-conditions.html, legal/terms-and-conditions.html, copyright-policy.html, "
             "hyperlinking-policy.html) all 404; website-policy.html is the one that exists.",
    ),

    TermsRecord(
        source_id="rbi",
        name="Reserve Bank of India",
        terms_url="https://www.rbi.org.in/Scripts/Disclaimer.aspx",
        date_read=READ_ON,
        clauses=(
            Clause(CACHING, PROHIBITED, _RBI_CACHING,
                   "The only one of the seven scraped web sources that addresses caching, "
                   "and it forbids it. Nothing from rbi.org.in may enter source_documents. "
                   "(The two CC-BY-4.0 datasets added later permit caching by licence.)"),
            Clause(COMMERCIAL_USE, PERMISSION_REQUIRED, _RBI_DEEP_LINK,
                   "Even LINKING to an internal page needs written permission, which is a "
                   "stricter gate than reproduction on most sites."),
            Clause(ATTRIBUTION, OPEN,
                   note="The disclaimer does not reach attribution. The three URLs that "
                        "would (copyright.aspx, Terms.aspx, Websitepolicy.aspx) are "
                        "SOFT-404s: each answers HTTP 200 with ~55KB of site shell and no "
                        "policy text, while the real page is ~63KB. payload_refusal() "
                        "cannot catch that -- HTML was expected and HTML arrived -- which "
                        "is the CLAUDE.md soft-404 failure in a new place."),
            Clause(RATE_LIMIT, OPEN,
                   note="Moot: the WAF refuses us outright."),
        ),
        robots=(
            RobotsResult(
                origin="https://www.rbi.org.in", state=BLOCKED, http=418, loaded=False,
                verbatim=_RBI_418,
                disallow_count=0, crawl_delay=None, effective_delay=2.0,
                paths={"https://www.rbi.org.in/Scripts/NotificationUser.aspx": False,
                       "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx": False}),
        ),
        note="**The terms pages were read BEFORE checker/robots.py learned that 418 is a "
             "refusal.** At the moment of the fetch, rules_for_status() read 418 as 'no "
             "rules published' and allowed() therefore permitted it; the same request "
             "returns 999 refused today. Recorded rather than quietly re-labelled, because "
             "the quote above is why the fix was made. RBI is BLOCKED and also PROHIBITS "
             "caching, so it is closed twice over and no connector may fetch it.",
    ),

    TermsRecord(
        source_id="egazette",
        name="e-Gazette (Department of Publication)",
        terms_url="",
        date_read="",
        clauses=(
            Clause(CACHING, OPEN, note="No policy page could be read."),
            Clause(ATTRIBUTION, OPEN, note="No policy page could be read."),
            Clause(COMMERCIAL_USE, OPEN, note="No policy page could be read."),
            Clause(RATE_LIMIT, OPEN,
                   note="No robots.txt exists, so no Crawl-delay; our 2s floor governs."),
        ),
        robots=(
            RobotsResult(
                origin="https://egazette.gov.in", state=NOT_FOUND, http=404, loaded=True,
                verbatim="404 - File or directory not found. (IIS, text/html, 1245 bytes)",
                disallow_count=0, crawl_delay=None, effective_delay=2.0,
                paths={"https://egazette.gov.in/WriteReadData/2026/x.pdf": True,
                       "https://egazette.gov.in/default.aspx": True}),
        ),
        note="A genuine 404 on robots.txt: the host answers and publishes no rules, which "
             "RFC 9309 reads as allowance and checker/robots.py honours. This is exactly "
             "the case that stopped 418 being fixed with a body-shape rule -- e-Gazette's "
             "404 is also text/html. Both WebsitePolicy.aspx and Terms.aspx answer HTTP "
             "500, so the terms are unread and every clause is OPEN. The homepage serves "
             "(200, 66KB) but a homepage is not a terms page. The Gazette is already "
             "fetched elsewhere in this repository under a registered SourceRecord "
             "(checker/provenance.py); this record governs the checker/sources path only.",
    ),

    TermsRecord(
        source_id="data_gov_in",
        name="data.gov.in / Open Government Data platform (GODL)",
        terms_url="",
        date_read="",
        clauses=(
            Clause(ATTRIBUTION, OPEN,
                   note="The GODL text was NOT read. PLAN_26 §3 quotes it from a search "
                        "summary; that is not a reading, so it is not repeated here."),
            Clause(COMMERCIAL_USE, OPEN, note="GODL unread -- see ATTRIBUTION."),
            Clause(CACHING, OPEN, note="GODL unread -- see ATTRIBUTION."),
            Clause(RATE_LIMIT, OPEN, note="GODL unread -- see ATTRIBUTION."),
        ),
        robots=(
            RobotsResult(
                origin="https://www.data.gov.in", state=BLOCKED, http=403, loaded=False,
                verbatim=_ACCESS_DENIED.format(host="data.gov.in"),
                paths={"https://www.data.gov.in/Godl": False,
                       "https://www.data.gov.in/government-open-data-license-india": False,
                       "https://www.data.gov.in/terms-and-conditions": False}),
            RobotsResult(
                origin="https://data.gov.in", state=ACCESSIBLE, http=200, loaded=True,
                verbatim="User-agent: *\nDisallow: /",
                disallow_count=1, crawl_delay=None, effective_delay=2.0,
                paths={"https://data.gov.in/Godl": False,
                       "https://data.gov.in/government-open-data-license-india": False,
                       "https://data.gov.in/terms-and-conditions": False}),
            RobotsResult(
                origin="https://api.data.gov.in", state=UNREACHABLE, http=-1, loaded=False,
                verbatim="<urlopen error [Errno 61] Connection refused>",
                paths={"https://api.data.gov.in/resource/": False}),
        ),
        note="**Closed two different ways, and the second one settles it.** The www host "
             "answers /robots.txt with a 403 Access Denied. The apex host DOES answer -- and "
             "publishes `User-agent: * / Disallow: /`, a blanket refusal of the whole site. "
             "Finding a second origin after a 403 is how a WAF gets worked around, so the "
             "apex was asked for /robots.txt and nothing else, and it said no. "
             "**This blocks S2 as designed**: MCA company master data cannot be taken from "
             "this platform by fetching it. The lawful route is the registered API-key "
             "service at api.data.gov.in, which refused the connection from this network "
             "and is a separate owner decision (a key, and the GODL text read at last).",
    ),

    TermsRecord(
        source_id="bse",
        name="BSE (Bombay Stock Exchange) announcements",
        terms_url="",
        date_read="",
        clauses=(
            Clause(CACHING, OPEN, note="No page could be read: robots.txt is a 403."),
            Clause(ATTRIBUTION, OPEN, note="No page could be read: robots.txt is a 403."),
            Clause(COMMERCIAL_USE, OPEN, note="No page could be read: robots.txt is a 403."),
            Clause(RATE_LIMIT, OPEN, note="No page could be read: robots.txt is a 403."),
        ),
        robots=(
            RobotsResult(
                origin="https://www.bseindia.com", state=BLOCKED, http=403, loaded=False,
                verbatim=_ACCESS_DENIED.format(host="bseindia.com"),
                paths={"https://www.bseindia.com/corporates/ann.html": False,
                       "https://www.bseindia.com/static/about/terms_conditions.aspx": False}),
        ),
        note="The same 403 checker/robots.py recorded on 2026-09-17, unchanged. It is why "
             "_DENIED exists. Nothing further was attempted.",
    ),

    TermsRecord(
        source_id="nse",
        name="NSE (National Stock Exchange) announcements",
        terms_url="",
        date_read="",
        clauses=(
            Clause(CACHING, OPEN, note="Policy pages unread -- the server drops us."),
            Clause(ATTRIBUTION, OPEN, note="Policy pages unread -- the server drops us."),
            Clause(COMMERCIAL_USE, OPEN, note="Policy pages unread -- the server drops us."),
            Clause(RATE_LIMIT, OPEN,
                   note="robots.txt publishes no Crawl-delay; our 2s floor would govern. "
                        "The connection behaviour below is the real limiter."),
        ),
        robots=(
            RobotsResult(
                origin="https://www.nseindia.com", state=ACCESSIBLE, http=200, loaded=True,
                verbatim="User-agent: *\nAllow: /\nDisallow: /market-data-test\n"
                         "Sitemap: https://www.nseindia.com/sitemap.xml",
                disallow_count=1, crawl_delay=None, effective_delay=2.0,
                paths={"https://www.nseindia.com/api/corporate-announcements": True,
                       "https://www.nseindia.com/market-data-test": False}),
        ),
        note="**The interesting one: robots says yes and the server says nothing.** "
             "/robots.txt serves cleanly and allows everything but one test path, and then "
             "/terms-conditions and /website-policies both time out at 45s and "
             "/regulations/website-policy answers 'Remote end closed connection without "
             "response'. Permission and access are different facts and this source has one "
             "without the other. It is NOT recorded as BLOCKED -- nothing refused us, we "
             "were dropped -- and the terms are unread either way, so no connector loads.",
    ),
    # ── AWS Open Data: eCourts judgments, CC-BY-4.0, managed by Dattam Labs ──────
    # Owner-approved. Added 2026-10-05 from the AWS Open Data Registry YAML and the CC-BY-4.0
    # deed, both fetched that day. These are the first two sources in this file whose terms
    # are a standard open-data LICENCE rather than a scraped website policy -- so caching is
    # permitted (CC-BY grants redistribution), which the self-test's headline finding now
    # reflects. Tier LICENSED: a judgment may support an answer, never make one VERIFIED.
    TermsRecord(
        source_id="aws_sc_judgments",
        name="Indian Supreme Court Judgments (AWS Open Data, Dattam Labs)",
        terms_url="https://registry.opendata.aws/indian-supreme-court-judgments/",
        date_read=READ_AWS,
        clauses=(
            Clause(CACHING, READ, quote=_CCBY_SHARE,
                   note="CC-BY-4.0 grants redistribution, so storing the metadata and the "
                        "judgment PDFs (with sha256) is permitted -- unlike every scraped "
                        "source in this file."),
            Clause(ATTRIBUTION, READ, quote=_CCBY_ATTRIBUTION,
                   note="Credit: Dattam Labs (https://dattam.in), from the eCourts website; "
                        "licence https://creativecommons.org/licenses/by/4.0/. Party from "
                        "the registry YAML; requirement from the CC-BY-4.0 deed."),
            Clause(COMMERCIAL_USE, READ, quote=_CCBY_COMMERCIAL),
            Clause(RATE_LIMIT, OPEN,
                   note="No published rate limit for anonymous S3 reads; our 2s courtesy "
                        "floor governs. UpdateFrequency per the registry: Bi-monthly."),
        ),
        robots=(
            RobotsResult(
                origin="https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com",
                state=NOT_FOUND, http=404, loaded=True, verbatim=_S3_NOSUCHKEY,
                disallow_count=0, crawl_delay=None, effective_delay=2.0,
                paths={"https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"
                       "/metadata/parquet/year=1950/metadata.parquet": True,
                       "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com"
                       "/data/pdf/year=1950/english/1950_1_15_25_EN.pdf": True}),
        ),
        note="AWS Open Data Registry dataset (arn:aws:s3:::indian-supreme-court-judgments, "
             "ap-south-1), ManagedBy Dattam Labs, License CC-BY-4.0, UpdateFrequency "
             "Bi-monthly, collected from the eCourts website; contact contact@dattam.in. "
             "Verified live 2026-10-05: the bucket reads anonymously (no credentials), "
             "metadata/parquet/year=YYYY/ and data/pdf/year=YYYY/english/<path>_EN.pdf, and "
             "a fetched PDF opened with the %PDF-1.7 magic bytes. The GOVERNING robots "
             "surface is the bucket's own virtual host, which answers /robots.txt with a 404 "
             "NoSuchKey (RFC 9309 allowance); Amazon's shared s3.ap-south-1 service root 403s "
             "a keyless request generically and is NOT this dataset's crawl directive. Tier "
             "LICENSED -- it may support an answer and never make one VERIFIED.",
    ),
    TermsRecord(
        source_id="aws_hc_judgments",
        name="Indian High Court Judgments (AWS Open Data, Dattam Labs)",
        terms_url="https://registry.opendata.aws/indian-high-court-judgments/",
        date_read=READ_AWS,
        clauses=(
            Clause(CACHING, READ, quote=_CCBY_SHARE,
                   note="CC-BY-4.0 grants redistribution; storing metadata and PDFs with "
                        "sha256 is permitted."),
            Clause(ATTRIBUTION, READ, quote=_CCBY_ATTRIBUTION,
                   note="Credit: Dattam Labs (https://dattam.in), from the eCourts website; "
                        "licence https://creativecommons.org/licenses/by/4.0/."),
            Clause(COMMERCIAL_USE, READ, quote=_CCBY_COMMERCIAL),
            Clause(RATE_LIMIT, OPEN,
                   note="No published rate limit for anonymous S3 reads; our 2s courtesy "
                        "floor governs. UpdateFrequency per the registry: Quarterly -- not "
                        "Bi-monthly like the Supreme Court set, which is why each is read "
                        "rather than assumed."),
        ),
        robots=(
            RobotsResult(
                origin="https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com",
                state=NOT_FOUND, http=404, loaded=True, verbatim=_S3_NOSUCHKEY,
                disallow_count=0, crawl_delay=None, effective_delay=2.0,
                paths={"https://indian-high-court-judgments.s3.ap-south-1.amazonaws.com"
                       "/metadata/parquet/": True}),
        ),
        note="AWS Open Data Registry dataset (arn:aws:s3:::indian-high-court-judgments, "
             "ap-south-1), ManagedBy Dattam Labs, License CC-BY-4.0, UpdateFrequency "
             "Quarterly, collected from the eCourts website. Same governing-robots reasoning "
             "as the Supreme Court record above: the bucket virtual host 404s /robots.txt. "
             "Tier LICENSED.",
    ),
)

_BY_ID = {r.source_id: r for r in RECORDS}
SOURCE_IDS = tuple(sorted(_BY_ID))


def record_for(source_id: str) -> TermsRecord:
    """The record, or NoTermsRecord. This is the gate a connector loads through."""
    try:
        return _BY_ID[source_id]
    except KeyError:
        raise NoTermsRecord(
            f"no terms record for {source_id!r}; nothing is fetched on an unread term "
            f"(PLAN_26 §3). Known: {', '.join(SOURCE_IDS)}") from None


def may_fetch(source_id: str) -> tuple[bool, str]:
    """May a connector for this source fetch at all, and why not.

    Three conditions, and all of them are about what was measured rather than what we
    would like: every robots origin must permit us, the terms must have been read, and
    nothing read may be a PROHIBITED clause.
    """
    rec = record_for(source_id)
    refused = [r for r in rec.robots if not r.permits]
    if refused:
        return False, (f"robots: " + "; ".join(
            f"{r.origin} {r.state} HTTP {r.http}" for r in refused))
    if not rec.terms_url:
        return False, "terms unread -- an unread term is OPEN, and OPEN is not permission"
    banned = [c.topic for c in rec.clauses if c.state == PROHIBITED]
    if banned:
        return False, f"the terms prohibit {', '.join(banned)}"
    return True, f"robots permit, terms read {rec.date_read}"


def may_cache(source_id: str) -> tuple[bool, str]:
    """May fetched bytes be stored in source_documents?

    Stricter than may_fetch, and separately asked, because the two are different
    permissions: RBI lets a browser read a page and forbids caching it in terms.

    Today this returns False for all seven scraped web sources: two prohibit or gate it and
    five never address it, and an unread term is OPEN. It returns True for the two CC-BY-4.0
    judgment datasets, whose licence grants redistribution. That is the finding, not a
    placeholder.
    """
    rec = record_for(source_id)
    ok, why = may_fetch(source_id)
    if not ok:
        return False, why
    c = rec.clause(CACHING)
    if not c.permits:
        return False, (f"caching is {c.state} for {source_id}: "
                       f"{c.quote or c.note or 'not addressed by the terms'}")
    return True, c.quote


def attribution_for(source_id: str) -> str:
    """The attribution the source requires, verbatim, or "" when it states none.

    Returns the clause's own words rather than a label we invented, so a caller that
    renders it cannot render something the terms do not ask for.
    """
    c = record_for(source_id).clause(ATTRIBUTION)
    return c.quote if c.state != OPEN else ""


def table() -> str:
    """The S0 table: source, terms status, robots status."""
    rows = [f"  {'source':<14}{'terms':<22}{'robots':<38}fetch?",
            f"  {'-' * 84}"]
    for r in RECORDS:
        terms = f"READ {r.date_read}" if r.terms_url else "OPEN (unread)"
        rob = "; ".join(f"{o.state}({o.http})" for o in r.robots)
        ok, why = may_fetch(r.source_id)
        rows.append(f"  {r.source_id:<14}{terms:<22}{rob:<38}{'YES' if ok else 'no'}")
    cache = [s for s in SOURCE_IDS if may_cache(s)[0]]
    rows += ["",
             f"  fetchable: {[s for s in SOURCE_IDS if may_fetch(s)[0]] or 'none'}",
             f"  cacheable: {cache or 'none -- two prohibit or gate it, five never say'}"]
    return "\n".join(rows)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("sources.terms")

    # The gate PLAN_26 §3 names: no record, no connector.
    try:
        record_for("manupatra")
        check(False, "an unknown source raises NoTermsRecord")
    except NoTermsRecord as e:
        check("unread term" in str(e), f"an unknown source raises NoTermsRecord ({e!s:.60})")
    check(issubclass(NoTermsRecord, LookupError),
          "...and it is an exception, not a warning a caller can ignore")

    # The invariant that stops OPEN becoming a place to park a paraphrase.
    try:
        Clause(CACHING, OPEN, "probably fine")
        check(False, "an OPEN clause cannot carry a quote")
    except ValueError as e:
        check("unread term has no words" in str(e),
              "an OPEN clause cannot carry a quote -- an unread term has no words")
    try:
        Clause(CACHING, READ, "   ")
        check(False, "a READ clause must carry its words")
    except ValueError as e:
        check("must say what it says" in str(e), "a READ clause must carry its words")
    for bad in [("NONSENSE", OPEN), (CACHING, "FINE")]:
        try:
            Clause(*bad)
            check(False, f"{bad} is refused")
        except ValueError:
            check(True, f"{bad!r} is refused -- topics and states are closed sets")

    # Every record states all four topics: an omitted topic reads as "fine".
    for r in RECORDS:
        check({c.topic for c in r.clauses} == set(TOPICS),
              f"{r.source_id}: all four topics stated")
    try:
        TermsRecord("x", "X", "", "", (Clause(CACHING, OPEN),),
                    (RobotsResult("https://x", NOT_FOUND, 404, True, "404"),))
        check(False, "a record missing a topic is refused")
    except ValueError as e:
        check("all four topics" in str(e), "a record missing a topic is refused")

    # A blocked source must carry the refusal it is claiming.
    try:
        RobotsResult("https://x", BLOCKED, 403, False, "")
        check(False, "BLOCKED with no recorded response is refused")
    except ValueError as e:
        check("no response recorded" in str(e),
              "BLOCKED with no recorded response is refused -- a refusal needs its evidence")

    # The measured verdicts. These are the S0 result, asserted so a later edit that
    # quietly opens a closed source has to break a test to do it.
    for sid in ("rbi", "data_gov_in", "bse"):
        allowed, why = may_fetch(sid)
        check(not allowed, f"{sid} may NOT be fetched ({why[:52]})")
    check(not may_fetch("nse")[0] and "terms unread" in may_fetch("nse")[1],
          "nse is refused for UNREAD TERMS, not for robots -- robots permits it")
    check(any(o.state == ACCESSIBLE for o in record_for("nse").robots),
          "...and the record says so: its robots result is ACCESSIBLE")
    check(not may_fetch("egazette")[0] and "terms unread" in may_fetch("egazette")[1],
          "egazette is refused for unread terms though its robots 404 permits it")
    check(record_for("egazette").robots[0].state == NOT_FOUND
          and record_for("egazette").robots[0].loaded,
          "...a 404 robots.txt is an ANSWER (allowance), not a block")

    for sid in ("indiankanoon", "sebi"):
        allowed, why = may_fetch(sid)
        check(allowed, f"{sid} may be fetched ({why})")
    check(may_fetch("sebi")[0] and not may_cache("sebi")[0],
          "sebi may be fetched and may NOT be cached -- the two are different permissions")

    # RBI is the case that proves may_cache is asked separately.
    check(record_for("rbi").clause(CACHING).state == PROHIBITED,
          "rbi PROHIBITS caching, in its own words")
    check("caching and links to" in record_for("rbi").clause(CACHING).quote,
          "...quoted verbatim, not summarised")
    check(not may_cache("rbi")[0], "...so may_cache says no")

    # The headline finding, asserted rather than described. Updated 2026-10-05 when the two
    # CC-BY-4.0 judgment datasets were added: an open-data LICENCE grants caching, which no
    # scraped website policy in this file does. Not a weakened test -- a new true state.
    check({s for s in SOURCE_IDS if may_cache(s)[0]} == {"aws_sc_judgments",
                                                         "aws_hc_judgments"},
          "only the two CC-BY-4.0 judgment datasets may be cached; none of the seven "
          "scraped web sources may")
    check(sum(may_fetch(s)[0] for s in SOURCE_IDS) == 4,
          "exactly 4 sources are fetchable (indiankanoon, sebi, and the two AWS judgment "
          "datasets)")

    # Attribution: the clause's own words, and IK's names RAG.
    a = attribution_for("indiankanoon")
    check("Retrieval-Augmented Generation" in a and "powered by IKanoon" in a,
          "IK attribution names RAG context and the logo, not just display")
    check("logo" in a,
          "...the LOGO: PLAN_26's 'Powered by IKanoon' text does not satisfy this clause")
    check(attribution_for("bse") == "",
          "an unread attribution clause yields the empty string, never an invented label")
    check("prominently acknowledged" in attribution_for("sebi"),
          "sebi attribution is quoted from its copyright policy")

    # PERMISSION_REQUIRED must not read as permission.
    check(PERMISSION_REQUIRED not in PERMISSIVE,
          "PERMISSION_REQUIRED is not permissive -- 'you may, after emailing us' is not a "
          "permission we hold")
    check(record_for("sebi").clause(COMMERCIAL_USE).state == PERMISSION_REQUIRED
          and not record_for("sebi").clause(COMMERCIAL_USE).permits,
          "...so sebi's reproduction clause does not permit reproduction")

    # No record may claim a reading with no date.
    for r in RECORDS:
        check(bool(r.terms_url) == bool(r.date_read),
              f"{r.source_id}: a terms URL and a read date travel together")

    # Every intended path decided, none left as a guess.
    for r in RECORDS:
        for o in r.robots:
            check(all(isinstance(v, bool) for v in o.paths.values()),
                  f"{r.source_id} {o.origin}: every intended path has a decision")

    check(len(table().splitlines()) >= len(RECORDS) + 2, "the S0 table renders")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(table())
