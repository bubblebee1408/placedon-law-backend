# What we can legitimately connect to, and what we cannot — 25 Sep 2026

Founder decision the same day: **free/official sources only**, no aggregator or case-law licence
budget. This document records what that buys and what it forecloses. Sources were fetched live by
the research agent; claims it could not verify are marked **[3P]** or "unconfirmed" and stay that way.

## 1. The finding that breaks the "connect your own account" thesis

**MCA21 has no OAuth, no delegation, and no API.** A customer **cannot** connect their MCA account
to us the way they connect Google Calendar to Claude. There is no mechanism to delegate. The portal
is WAF-protected and returns HTTP 403 to every automated client — including its own policies PDF,
which is why its terms remain **[3P], unverified**; read them in a browser before relying on them.

So the Harvey/Spellbook-style connector model works for **document systems** (Microsoft 365, Google
Workspace, iManage, NetDocuments, DocuSign) and **not** for the Indian statutory registry that our
product is actually about. The compliant analogue is **customer-in-the-loop**: the customer buys the
document from MCA21's "View Public Documents" themselves and uploads it. That is the only documented
path that respects MCA's terms, and it is also why our "no upload" design will eventually need
revisiting — not for convenience, but because it is the only lawful inbound route for filing data.

## 2. There is no MCA aggregator licence to contract for

`checker/corporate_data.LicensedAggregatorProvider` is stubbed "awaiting a contracted,
MCA-sanctioned aggregator". The research found **no MCA programme page, no list of authorised
aggregators, and no vendor publishing an MCA licence.** Surepass claims only that its "system checks
the information from the MCA department"; Probe42 describes aggregating "740+ public sources".

So the stub awaits a **private commercial data-supply agreement**, not a government licence. If we
ever buy one, the thing actually being bought is a **written representation and warranty that the
supplier has lawful rights to collect and redistribute, plus indemnity** — because none of them
publishes a licence, that warranty *is* the product. The question to ask any of them is: *"do you
hold a written agreement with MCA, and may we see it under NDA?"* Their answer is the decision.

The only officially sanctioned MCA bulk routes are **data.gov.in under GODL-India** (commercial use
permitted, attribution mandatory, Company Master Data updated 22-07-2026) and the **Corporate Data
Management research scheme** (research-scoped, committee approval).

## 3. Tier 0 — free, verified working, and enough for a beta

| Source | Status | Terms |
|---|---|---|
| **India Code** DSpace 9.1 REST | **verified** — `discover/search/objects?query=Companies Act` → 13,340 results; Companies Act 2013 ORIGINAL bundle → 288-page PDF, HTTP 200 | no rights metadata; statutory basis is Copyright Act s.52(1)(q) |
| **data.gov.in** MCA Company Master Data | catalog API + ZIP, GODL-India | commercial use permitted, attribution mandatory |
| **SEBI RSS** | verified live | no stated terms; robots.txt permits |
| **eCourts / eSCR** | free web | reproduction permitted **with prominent source acknowledgement** |
| **Supreme Court judgments, AWS Open Data** | ~35k judgments 1950–, ~52 GB | **CC-BY-4.0** — applied by the dataset maintainer, **not** by the Court |
| **eGazette** | free, human/browser download only | matches our existing human-attested flow; keep it |

**Operational trap, verified on this machine today:** use the **apex** host
`https://indiacode.gov.in/server/api`. Measured: apex → **HTTP 200**; `www.indiacode.gov.in` →
**connection failure (000)**, consistent with the reported cert mismatch. `backend.indiacode.gov.in`
is reported a populated-zero instance that answers but returns 0 communities. **Code pointing at the
wrong host returns nothing, silently** — the worst failure shape this repo has.
**Action taken: none yet.** `checker/provenance.py:63` lists `www.indiacode.gov.in` among permitted
hosts. It fails closed (TLS), so nothing is served wrongly — but a record whose `source_url` uses
that host can never be re-verified. Logged, not silently edited, because provenance hosts are a
deliberate list and changing one needs its own commit and test.

## 4. Tier 1 — the one commercial source worth the money

**Indian Kanoon's API is the standout.** Its terms are the only ones found that **explicitly permit
RAG and LLM fine-tuning**, conditional on a "powered by IKanoon" attribution logo. Pricing is public:
**₹0.20 per document**, ₹0.50 per search, ₹500 free credit on signup, ₹10,000/month free for verified
non-commercial use.

For any judgment-tracking or case-outcome feature, this is the entry point — not SCC Online or
Manupatra. **Manupatra's subscriber agreement bans robots (cl. 9.3) and bans storing content in an
archival or searchable database (cl. 9.9)**, which forecloses exactly what we would want to do, and
it has reportedly entered an exclusive AI partnership elsewhere **[3P]** which may close the door
regardless.

## 5. Closed to machine access entirely

MCA21 V3 · NJDG Open API (**Central/State Government only**; DoJ says expansion to others is
"proposed") · NCLT · NCLAT · IBBI · RBI circulars (its disclaimer prohibits **caching** and framing
without written permission; whether that reaches server-side storage is **unresolved**).

## 6. Two legal questions for counsel, not for us

1. **Copyright Act s.52(1)(q)(ii)** permits reproducing an Act *"subject to the condition that such
   Act is reproduced or published together with any commentary thereon or any other original
   matter."* **Whether an AI product's generated analysis satisfies "commentary … or other original
   matter" is a genuine open question.** Our entire corpus rests on it. Do not resolve this
   internally.
2. **data.gov.in's `robots.txt` is `Disallow: /`** while the same portal runs an API-key programme
   for the same datasets. Safe reading: use the key and the ZIP, never crawl the HTML. It also
   currently renders a *"sandbox environment … for testing and demonstration purposes only"* banner,
   whose status is unclear.

## 7. Connectors, ranked for a beta

1. **Microsoft Graph** (OAuth 2.0 + Entra ID) — largest install base among Indian in-house/CS teams,
   free to build against, multi-tenant app + admin consent.
2. **Google Workspace** — budget for **OAuth verification + CASA security assessment**, 4–8 weeks.
3. **DocuSign** — free dev account, but a **Go-Live app review** before production.
4. Defer **iManage** and **NetDocuments** (both need vendor-side registration).
5. **Tally is not a connector.** XML over HTTP on port 9000 / ODBC / TDL, requiring a running Tally
   instance on the customer's LAN. It is an **on-prem agent**, architecturally unlike everything else.
