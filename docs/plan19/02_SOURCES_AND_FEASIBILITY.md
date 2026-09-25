# 02: Every requested source, whether we may use it, and what it would be worth

The rule applied is `CLAUDE.md`'s:

- permitted sources only;
- no bypassing a WAF, robots rules or terms;
- a 404 or a block is evidence of nothing.

A source enters the product only if it can carry four things on every fact it contributes: where
it came from, when it was true, whether we may redistribute it (PLAN_08 Axis D), and which ring it
lands in.

## 1. Summary

| Source | Asked for | May we use it? | Ring | Worth to the wedge | Decision |
|---|---|---|---|---|---|
| India Code REST (apex host) | law | **Yes** [R: `docs/research/DATA_ACCESS_AND_CONNECTORS_2026_09_25.md` §3] | 0 | Core | Held |
| eGazette | law changes | Yes, human/browser download [R, same doc] | 0 | Core: this is where currency comes from | Built (`checker/feeds/egazette.py`) |
| SEBI RSS | regulator news | Yes, robots permits [R, same doc] | 2 | High for listed clients | G3 |
| data.gov.in MCA Company Master Data | company facts | Yes, GODL-India, attribution mandatory. Use the API key and ZIP, never crawl the HTML [R, same doc §6] | 1 | High: the only sanctioned bulk MCA route | G3 |
| IBBI, OFAC SDN | counterparty status | Built feeds [R: `checker/feeds/`] | 1–2 | High (s.185/188 counterparties) | Built / G6 |
| Supreme Court judgments, AWS Open Data | case law | Yes. CC-BY-4.0, **applied by the dataset maintainer, not the Court** [R, same doc] | 2 | High, as a citator | G5 |
| eCourts / eSCR | case law | Reproduction permitted with prominent acknowledgement [R, same doc] | 2 | Medium | G5, after SC |
| Indian Kanoon API | case law | Terms permit RAG and fine-tuning with attribution; ₹0.20/doc [R, same doc §4] | 2 | High | **[BLOCKED]**: founder chose free sources only on 2026-09-25 |
| GDELT | international news | Commercial use without fee; redistribution with citation and link [V] | 2 | **Low**: context, never authority | G3, optional |
| NSE market data and announcements | stock market | **No, not by scraping.** Terms prohibit automated collection; commercial market data is licensed [S] | — | Medium for listed clients | **Do not build.** Licensed vendor only, after revenue |
| Zauba shipment data | import/export | **Unknown.** Terms unreadable from here; the provenance of Indian shipment-level data is unexplained | — | Low for the wedge | **Do not build** |
| Reddit | practitioner language | Language and pain points only, never authority; OAuth is founder-owned (H-004) | none | Gold-set phrasing only | Existing rule |
| Judgment prediction | forecasting | See 04 §7 | — | Negative | **Do not build** |

## 2. NSE and the stock market

**What was found [S].** A search returned text attributed to NSE's own terms and data policy
pages. Direct fetch was **blocked by this environment's egress proxy**, so nothing below was read
first-hand.

- "Users are prohibited from conducting any systematic or automated data collection activities
  including scraping, data mining, data extraction and data harvesting" on the NSE website or app.
- "Market Data" is defined to include real-time, delayed, end-of-day, historical **and corporate
  data**.
- Market data accessed for commercial purposes is provided by NSE Data at a Board-approved price.
- A separate agreement applies to index creation.
- NSE lists authorised data vendors.

**Consequence.** Scraping NSE announcements or prices is out, whatever the technical ease. A
licensed feed is possible, but it is a contract, and a price nobody has quoted us. **[OPEN]:** read
`nseindia.com/static/nse-terms-of-use` and the Data Usage and Sharing Policy PDF in a browser, and
quote them before any decision.

**Is it worth it?** Only for listed-company clients, and only for three things: SEBI LODR
disclosures, SAST thresholds and insider-trading windows. All three are bodies of law we **do not
hold** (`checker/scope.py`). Price data carries no weight in a Companies Act question. **Do not
buy market data before we hold SEBI law.** A price feed without the regulation it would be checked
against is a ticker, not an audit.

## 3. Zauba and shipments

**What was found [S].** Zauba still operates (`zauba.com/shipment_search`). A data-marketplace
listing says it gathers records from "shipping manifests, bill of lading, bill of entries, and
shipping bills". Third-party scrapers of Zauba are sold on Apify. Zauba's terms page was
**egress-blocked** and was not read.

**The unresolved contradiction.** PLAN_08 §5 recorded that DGCI&S does not release shipment-level
Indian trade data at any price, as a matter of policy [R: `docs/PLAN_08_BOOKMARK_AND_GODSEYE.md`].
If that holds, Indian bill-of-entry-level data on a commercial site has a provenance nobody has
explained. We cannot give a record from it a `source_url` that a lawyer could re-verify, and we
cannot state its licence.

That is not an accusation against Zauba. It is the absence of the chain of title that
`checker/provenance.py` requires.

**Is it worth it?** For corporate compliance: close to nothing. Shipment volume does not decide
any Companies Act duty. The closest use, spotting related-party trade for s.188, needs the
counterparty's identity, which shipment records mask or which varies by source [OPEN].

**Decision: do not build.** To reopen it, three things must be true:

1. Zauba's terms are read and quoted, and permit commercial reuse.
2. Zauba states its upstream source in writing.
3. A named compliance question is found that shipment data decides.

## 4. International news (GDELT)

**What was found [V].** GDELT's About and Data pages state its datasets are available "for
unlimited and unrestricted use for any academic, commercial, or governmental use of any kind
without fee". Redistribution is permitted with a citation and a link.

**Is it worth it?** Low, and here is why rather than a shrug:

- News is never authority. A report that "the MCA will amend s.135" is not an amendment.
- At most, news tells us something may be coming, which is a reason to poll eGazette sooner.
  That is a scheduling signal, not a finding.

**Decision: G3, optional.** GDELT lands in Ring 2 with output class `SIGNAL` (`event_log.py`) [R].
It is never shown as fact, and it is attributed on screen as its terms require.

## 5. Case law: the citator

The request was "case law and judgment prediction". These are different products, and only one
survives (see 04 §7 for why prediction does not).

**The citator question.** Given a judgment a document or an answer relies on, has a later
judgment overruled, reversed, or doubted it?

- Bloomberg Law sells this as BCite, Westlaw as KeyCite, LexisNexis as Shepard's.
- It is the case-law analogue of what Themis already does for statutes: **currency**.
- It is deterministic on the citation graph once treatments are labelled.
- A stale citation is the case-law twin of the stale ₹4 crore threshold (PLAN_00).

**Sources, free only.**

- The Supreme Court corpus on AWS Open Data: about 35k judgments from 1950, about 52 GB,
  CC-BY-4.0, applied by the maintainer [R, DATA_ACCESS doc].
- eCourts/eSCR, with acknowledgement.

**[OPEN]: whether the maintainer's CC-BY grant is valid for court text is a question for
counsel.** It sits with the s.52(1)(q) question already raised in the same doc §6.

**What is hard.**

- **Extracting citations** is pattern work: SCC, AIR and SCR reporters, and neutral citations
  from 2023. It can be measured against a hand-checked sample.
- **Treatment classification** (followed, distinguished, overruled, doubted) is a language
  judgement. A model may propose one; a human labels it. The citator serves only human-labelled
  treatments as fact. Model proposals are shown as `SIGNAL` with the sentence that supports them.

**Hugging Face resources [V, licences not all read].**

- `law-ai/InLegalBERT` (Paul, Mandal, Goyal, Ghosh, ICAIL 2023) is pre-trained on Indian legal
  text. It is a candidate encoder for the treatment classifier.
- `opennyaiorg/InLegalNER` is a dataset. Its NER models are listed as Apache-2.0 [S]. It could
  help extract court, judge and statute mentions.
- `Exploration-Lab/IL-TUR` is gated, and its licence is **unread [OPEN]**. It is an evaluation
  reference, not training data, until the licence is read.

## 6. What "market-wide monitoring" becomes, honestly

The founder's picture is a screen that watches everything. What the permitted sources support is
a screen that watches **everything that can change a client's legal position under law we hold**:

1. **Law changes:** eGazette, and India Code revisions. Built.
2. **Counterparty status:** IBBI, OFAC, MCA master data, and the SEBI debarred list. Partly built.
3. **Case-law currency:** the citator (G5).
4. **Context signals:** SEBI RSS and GDELT, shown as `SIGNAL`, never fact.

Everything else on the founder's list either needs a contract, has no chain of title, or answers
a question the product does not ask.

## Sources

- NSE terms (search summary; fetch blocked): https://www.nseindia.com/static/nse-terms-of-use
- NSE data policy: https://www.nseindia.com/static/market-data/nse-data-policy
- NSE Data Usage and Sharing Policy PDF: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_DataUsageandSharingPolicy.pdf
- Zauba shipment search (fetch blocked): https://www.zauba.com/shipment_search
- Zauba on Datarade: https://datarade.ai/data-providers/zauba/profile
- GDELT: https://gdeltproject.org/about.html · https://gdeltproject.org/data.html
- InLegalBERT: https://dl.acm.org/doi/10.1145/3594536.3595165 · https://huggingface.co/law-ai/InLegalBERT
- InLegalNER: https://huggingface.co/datasets/opennyaiorg/InLegalNER · https://github.com/Legal-NLP-EkStep/legal_NER
- IL-TUR: https://huggingface.co/datasets/Exploration-Lab/IL-TUR
- Repository: `docs/research/DATA_ACCESS_AND_CONNECTORS_2026_09_25.md`, `docs/PLAN_08_BOOKMARK_AND_GODSEYE.md` §5, `docs/PLAN_14_TERMINAL_AND_FEEDS.md` §3
