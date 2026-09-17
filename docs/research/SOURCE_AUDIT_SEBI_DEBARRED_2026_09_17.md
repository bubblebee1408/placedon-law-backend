# Source audit — SEBI debarred entities, 2026-09-17

**Question.** Can Themis carry the SEBI debarred-entities list as a live Ring 2 feed,
servable to paying customers? PLAN_08 §5 named it as the next feed after OFAC SDN.

**Result: NOT BUILT. Every route checked is blocked, forbidden, or paid.** Nothing was
bypassed. This file exists so nobody spends the afternoon rediscovering it.

---

## Sources checked

| Source | Access (measured, honest `PlacedonBot/1.0` UA) | Terms | Verdict |
|---|---|---|---|
| **NSE** `nseindia.com/static/regulations/member-sebi-debarred-entities` | robots.txt 200, allows all but `/market-data-test`. **But the page itself: HTTP/2 stream reset in 0.05 s; HTTP/1.1 hangs to the 30 s timeout.** Archives host `nsearchives.nseindia.com`: same reset | Not reached | **BLOCKED** — bot protection rejecting non-browser clients. Not bypassed: spoofing a browser user agent or priming cookies to get past it is exactly the access-control circumvention `CLAUDE.md` forbids |
| **BSE** `bseindia.com` | **robots.txt itself returns an Akamai "Access Denied" 403** | Not reached | **BLOCKED** |
| **MSEI** `msei.in/Investors/List-of-Debarred-Entities` | robots.txt 404 (RFC 9309: allow). Page 200. File `List-of-Debarred-Entity-SEBI_11_09_2026.xlsx`, 1,506,822 bytes, ~4,892 rows | **Forbids it.** Quoted below | **FORBIDDEN by terms** |
| **OpenSanctions** `in_nse_debarred` | Public dataset page | *"Creative Commons 4.0 Attribution NonCommercial"* — *"Businesses must acquire a data license"* | **PAID** — CONTRACT_ONLY once licensed. 30,757 entities (14,441 targets), updated daily, upstream is NSE |
| **SEBI** `sebi.gov.in` | robots.txt 200, disallows only `/js` and `/css` | A "Disclaimer" entry exists but is script-loaded; `/copyright-policy.html` and `/website-policies.html` both 404 | **UNVERIFIED** — terms not found. SEBI issues the underlying orders, so this is the primary-source route if its terms permit |

### MSEI's terms, verbatim — `msei.in/disclaimer/default`

> "Except as otherwise provided you may not reproduce, republish, download, post, copy,
> store (either in hardcopy or otherwise), transfer, transmit, extract or otherwise
> distribute the Contents in any manner without the prior written permission of
> Metropolitan Stock Exchange of India Ltd.. You may only view and print one copy of the
> Contents for your own personal, non-commercial purpose…"

A feed fetches (downloads), caches (stores) and parses (extracts). It would breach three of
those verbs before serving anything.

---

## A mistake made during this audit — recorded

**S9. The MSEI file was downloaded and parsed before its terms were read.** Robots.txt was
checked; the terms of use were not. Those govern different things: robots.txt governs
*crawling*, the terms govern *what may be done with the content*. A clean robots file is
not permission.

Handling: the single inspection copy was deleted from the session scratchpad the moment the
terms were read. Nothing entered the repository, no cache, no commit. Verified by
`git status`.

**Rule this adds:** read the source's terms of use **before the first fetch of content**,
not after. Robots.txt alone is not a green light.

---

## Two further findings

**1. Personal data.** The list identifies entities by **PAN**, and a large share of rows are
individuals. An individual's PAN is personal data under the Digital Personal Data Protection
Act, 2023. An exchange publishing it does not by itself license a third party to store and
resell it. Whatever route is chosen, this needs a DPDP position *before* individuals' PANs
are stored or served. **OPEN — not decided here.**

**2. `checker/robots.py` reads a firewall 403 as permission.** `fetch_rules()` treats any
4xx robots.txt response as "no rules published", i.e. full allowance, per RFC 9309. BSE's
robots.txt returns **403 Access Denied from Akamai** — a block, not an absence. Under the
current code, a BSE fetch would pass the robots gate. It would then almost certainly be
blocked at the content request anyway, so nothing leaks today. But the gate's verdict is
wrong, and it should distinguish 401/403 (access denied) from 404/410 (no file). RFC 9309
§2.3.1.3 groups all 4xx as "unavailable", so this is a deliberate tightening beyond the RFC.
**OPEN — not changed here.**

---

## Unresolved

- SEBI's own reuse terms (UNVERIFIED).
- NSE's terms of use — never reached; the page is blocked.
- The DPDP position on individuals' PANs.

## Recommended next action

Decide one route; each is a founder decision, not an engineering one:

1. **OpenSanctions commercial licence** — fastest; they have already solved "may I show this
   to a paying customer". Upstream is still NSE, and the licence is theirs to warrant.
2. **Written permission from MSEI or NSE** — the terms explicitly offer "prior written
   permission".
3. **Derive from SEBI's own orders** on `sebi.gov.in` — primary source, but its terms are
   unverified, and it means parsing orders rather than one list.

**Meanwhile, the feed with no licence question at all is the Gazette.** `CLAUDE.md` names
"official legislation, Gazette" as a permitted source outright, and a Gazette watcher closes
D-1 — the amendment corpus that stopped in 2023 with nothing watching. That is the
terminal's ticker (PLAN_15 §0), and it needs no one's permission.
