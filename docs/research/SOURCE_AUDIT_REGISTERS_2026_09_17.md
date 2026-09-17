# Source audit — counterparty registers (SEBI orders, IBBI, MCA, RBI, CIBIL), 2026-09-17

**Question.** PLAN_08 §5 names four registers for the counterparty risk-and-status overlay —
MCA's Defaulter Companies / struck-off / disqualified-director lists, SEBI debarred entities,
IBBI corporate-debtor master data and public announcements, RBI suit-filed wilful defaulters —
plus a fifth, CIBIL suit-filed/wilful-defaulter data, as the private-sector alternative RBI's
own scheme document turns out to point at. For each: can Themis lawfully carry it as an
automated feed whose data is shown to paying customers? This audit checks the route the prior
`SOURCE_AUDIT_SEBI_DEBARRED_2026_09_17.md` left open — "derive from SEBI's own orders on
`sebi.gov.in`... its terms are unverified" — and does the same for IBBI, MCA, RBI and CIBIL.

**Result: one clean BUILDABLE (IBBI), two FORBIDDEN by terms as currently written (SEBI, RBI),
two BLOCKED outright (MCA, CIBIL). Nothing was bypassed; MCA and CIBIL were not probed beyond
one honest-UA request each.** SEBI's own copyright policy gates reproduction on emailed
permission, which was not sought here. RBI's own terms forbid caching of "any of the contents,"
and a feed caches by definition. IBBI is the one register whose own Copyright Policy grants
free reproduction "without requiring specific permission," subject only to accuracy and source
credit. Every register below identifies individuals (PAN, DIN, or name) and needs a DPDP Act
2023 position before anything is stored or served — that position is not decided here.

---

## Sources checked

| Source | Access (measured, honest `PlacedonBot/1.0` UA) | Terms | Verdict |
|---|---|---|---|
| **SEBI** `sebi.gov.in` (own enforcement orders) | robots.txt 200, disallows only `/js`, `/hindi/js`, `/css`, `/hindi/css` (0.25s). Orders are individual HTML pages under `/enforcement/`, indexed in `sitemap.xml`; no RSS/machine-readable feed found in the homepage `<head>` or footer | Found at `website-policy.html` (linked from `js/footer.js`, not the homepage DOM — matches the prior audit's "script-loaded" note). **Copyright Policy requires emailed permission before reproduction.** Quoted below | **FORBIDDEN by terms** — as written, until permission is requested and granted |
| **IBBI** `ibbi.gov.in` (corporate-debtor data, public announcements) | `www.ibbi.gov.in/robots.txt` 301s to `ibbi.gov.in/robots.txt`, which is a genuine 404 ("An Internal Error Has Occurred — Not Found") — no robots.txt exists, not a WAF block. Site reachable, 200s throughout | Found at `ibbi.gov.in/home/website-policy`. **Copyright Policy grants free reproduction "without requiring specific permission,"** subject to accuracy and source credit. Quoted below | **BUILDABLE** — with attribution, excluding any content the page separately marks as third-party copyright |
| **MCA** `www.mca.gov.in` | robots.txt: **403 Access Denied from Akamai** (4.9s). Homepage: **403** (0.06s). Confirms `CLAUDE.md`'s recorded state; not probed further, no workaround attempted | Not reached | **BLOCKED** |
| **RBI** `rbi.org.in` (wilful-defaulter scheme) | `www.rbi.org.in/robots.txt`: **418 "Unauthorised Access"** — a real application-level block, reproduced 3/3 attempts, all sub-second. The rest of the site (homepage, Disclaimer page, the scheme's own explainer page) returns 200 to the same UA — the block is specific to the `/robots.txt` path itself | Found at `Scripts/Disclaimer.aspx`. **"Caching... of this Web Site or any of the contents are prohibited"** except by written permission. No "commercial use" clause found on this page — SOURCE_POLICY's claim of that specific wording is UNVERIFIED, not confirmed. RBI's own scheme document (`rbidefaulterslist/index.html`) confirms in its own words that raw defaulter data is confidential bank-to-bank circulation, not a public database | **FORBIDDEN by terms** — a feed caches by definition, and caching is the one thing the terms name outright |
| **CIBIL** (TransUnion CIBIL) `cibil.com`, `transunioncibil.com`, `suit.cibil.com` | **403 from Cloudflare ("Sorry, you have been blocked") on every path tried** — `cibil.com/robots.txt` (0.17s), `www.cibil.com/`, `www.transunioncibil.com/`, and via WebFetch on `suit.cibil.com/` and a `transunioncibil.com/suit-filed-cases/overview` — same result through a second honest client | Not reached directly. A WebSearch summary attributed to `suit.cibil.com` quoted apparent language against "reproduced, copied, stored or archived... for sale or such other commercial purposes" — this is a second-hand, AI-generated search snippet, **not** an independently fetched quote, and is not treated as evidence per se | **BLOCKED** |

---

## Terms, verbatim, with their URLs

### 1. SEBI Copyright Policy — `sebi.gov.in/website-policy.html`

> "Material featured on this Website may be reproduced free of charge after taking proper
> permission by sending a mail to us. However, the material has to be reproduced accurately
> and not to be used in a derogatory manner or in a misleading context. Wherever the material
> is being published or issued to others, the source must be prominently acknowledged. However,
> the permission to reproduce this material shall not extend to any material which is identified
> as being copyright of a third party. Authorisation to reproduce such material must be obtained
> from respective copyright holders concerned."

This is not open reuse. It is structurally the same shape as MSEI's clause in the prior audit
("you may not reproduce... without the prior written permission of..."): reproduction is
conditioned on asking first. Nobody has asked. The page was reached only via a link buried in
`js/footer.js` (`document.write("...href='https://www.sebi.gov.in/website-policy.html'...")`) —
the homepage DOM itself carries no visible policy link, confirming the prior audit's "script-loaded"
finding, though the destination page itself is a plain static HTML file, reachable with `curl`.

### 2. IBBI Copyright Policy — `ibbi.gov.in/home/website-policy`

> "Material featured on this site may be reproduced free of charge in any format or media
> without requiring specific permission. This is subject to the material being reproduced
> accurately and not being used in a derogatory manner or in a misleading context. Where the
> material is being published or issued to others, the source must be prominently acknowledged.
> However, the permission to reproduce material on this site does not extend to any material
> which is explicitly identified as being the copyright of a third party. Authorisation to
> reproduce such material must be obtained from the copyright holders concerned."

Same page also carries a Hyperlink Policy ("We do not object to you linking directly to the
information hosted on this site, and no prior permission is required for the same") and a
Terms of Use disclaiming accuracy, consistent with the Copyright Policy being the operative
clause for a feed.

### 3. RBI Terms & Conditions of Use — `rbi.org.in/Scripts/Disclaimer.aspx`

> "Except as set forth below, caching and links to, and the framing of this Web Site or any
> of the contents are prohibited. Linking to the Home Page - You may link to the Home Page of
> this Web Site... upon notifying RBI in writing. For hyper-Linking to an internal page of this
> Web Site (not being the Home Page) the user must make a specific request for, and secure
> permission from RBI prior to hyper-linking to, or framing, this Web Site or any of the
> contents..."

This confirms `SOURCE_POLICY.md`'s "caching" claim in RBI's own words, verbatim. It does **not**
confirm the "commercial use" half of that same line — no such clause was found on this page, and
none was found elsewhere reached in this audit. That half of `SOURCE_POLICY.md:29` is now
UNVERIFIED rather than SOURCED; it may be true, on a page not reached here, but this audit did
not find it and does not assert it.

### 4. RBI's own account of the wilful-defaulter scheme — `rbi.org.in/rbidefaulterslist/index.html`

> "The Reserve Bank of India will circulate to the banks and FIs the information on the
> defaulters (i.e. advances classified as doubtful and loss) for their confidential use...
> Banks and FIs will not make available to any outside agency, without the prior approval of
> the Reserve Bank of India, information on defaulters received by them from the Reserve Bank
> of India."
>
> "Particulars of wilful defaulters against whom suits have been filed are published annually
> as on March 31 along with the list of suit-filed accounts of Rs.one crore and above in
> booklet/CD form... these booklets/CDs will be appropriately priced."

This is RBI's own primary confirmation of PLAN_08 §5's caveat — "RBI runs no searchable public
database; it is a classification banks apply." The bulk of the underlying classification
(doubtful/loss assets) is explicitly confidential, bank-to-bank. Only the narrower "suit-filed"
subset is published, historically as a **priced** booklet/CD, now also placed on the website —
and that website placement is exactly the content the Disclaimer's no-caching clause governs.

### 5. CIBIL — INFERRED path only, not independently confirmed

No page under `cibil.com`, `transunioncibil.com`, or `suit.cibil.com` was reachable with an
honest UA through either `curl` or WebFetch; all returned Cloudflare's block page. A WebSearch
result surfaced language purportedly from `suit.cibil.com` — "shall not be... reproduced,
copied, stored or archived in any manner, format or medium whatsoever, either in full or in
parts, for sale or such other commercial purposes" — but this is a search engine's own summary
of indexed content, not a page this audit fetched and read directly. Per `CLAUDE.md`, paraphrase
is not evidence; this is recorded as an unverified lead, not a source.

---

## Findings

- **This audit closes the prior SEBI-orders unresolved item**, but not in the direction that
  helps: SEBI's own terms require permission before reproduction, the same shape as MSEI's
  clause the prior audit already called FORBIDDEN. The two routes to the same underlying fact
  (SEBI debarment/enforcement data) — via NSE's `.xls` or via SEBI's own orders — are now both
  closed on the same defect: reproduction conditioned on asking first, and nobody has asked.
- **IBBI is the one register that is actually open.** Its Copyright Policy is the IBBI-side
  match of the NSE/MSEI/SEBI pattern, but with the permission requirement removed — "without
  requiring specific permission" is the operative difference. A feed built from IBBI's public
  corporate-debtor and public-announcement data, with source attribution on every record, matches
  the terms as written.
- **RBI's caching clause is fatal to a Ring 2 feed by its own architecture.** PLAN_08 §4 defines
  an OBSERVATION as requiring a `chain_hash` and both `observed_at` and `ingested_at` — i.e. a
  stored, timestamped copy. RBI's terms name caching specifically, not just commercial resale.
  Even setting aside the unverified "commercial use" half of `SOURCE_POLICY.md:29`, the verified
  half alone forbids what a feed is.
- **RBI's own document reroutes the practical question to CIBIL** — the underlying wilful-default
  classification is bank-confidential; only a narrow, historically-priced, published subset ever
  reaches the public, and RBI's terms forbid caching that subset too. CIBIL was the next hop and
  is fully BLOCKED at the access layer, before terms could even be read.
- **DPDP Act 2023 — every register here identifies individuals**, not just companies: SEBI
  orders name individuals and quote PAN directly (seen in the sitemap crawl, e.g. an order naming
  "Mrinal Verma... PAN ADDPV0274F"); IBBI's data includes named insolvency professionals; MCA's
  disqualified-director list is DIN-and-name by construction; RBI's suit-filed list names
  proprietors and directors; CIBIL's entire register is individual credit data. Whichever of
  these is eventually built needs a DPDP position on storing and serving that identification
  before it is built. **OPEN — not decided here**, per instruction.
- **MCA's WAF block was confirmed, not probed.** One robots.txt request and one homepage
  request, both honest-UA, both 403 from Akamai. No header manipulation, no retry with a
  different UA, no cookie priming — consistent with `CLAUDE.md`'s "do not bypass the MCA WAF."

---

## Unresolved

- SEBI's permission request was not sent; whether SEBI would grant it for an automated
  commercial feed is unknown.
- RBI's "commercial use" clause, if it exists, was not found — a different page than the
  Disclaimer (e.g. a Database on Indian Economy / `data.rbi.org.in` terms page, not reached; its
  homepage carried no visible policy links to follow) may carry it.
- CIBIL's actual terms were never independently read — access was blocked before any page could
  be fetched by any honest method tried.
- Whether IBBI's specific corporate-debtor and public-announcement data pages carry any terms
  narrower than the site-wide Copyright Policy was not separately checked; only the general
  Website Policy page was read.
- The DPDP Act 2023 position for all five registers.

## Recommended next action

Founder decisions, not engineering ones:

1. **IBBI is the one register buildable today** on its own published terms — attribute every
   record, exclude nothing marked third-party copyright, and resolve the DPDP question before
   anything with a name attached to it is stored.
2. **Send SEBI the permission request** its own Copyright Policy asks for, by email, and get the
   answer in writing before building anything from `sebi.gov.in` orders. Cheap to ask; the prior
   audit's NSE/MSEI route is closed on the identical clause, so this is the only surviving SEBI
   route worth the ask.
3. **RBI and CIBIL are not worth further engineering time on this pass.** RBI's own terms forbid
   caching outright, and its own scheme document shows the underlying classification is bank-
   confidential by design. CIBIL is blocked at the wall before terms are even legible. Revisit
   only if a licensed commercial CIC data reseller (the OpenSanctions-shaped move from the prior
   audit) turns out to also carry suit-filed/wilful-defaulter data — not confirmed here, not
   assumed.
4. **MCA stays closed.** Nothing changed; nothing was attempted to change it.
