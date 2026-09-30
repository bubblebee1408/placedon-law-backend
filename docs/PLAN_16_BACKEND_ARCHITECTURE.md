# PLAN 16 — the backend a user actually meets

Started 25-09-2026. **This is the spine, not the finished plan.** Three research streams are
running (token economics, vault/verification architecture, compliance + DPDP); their numbers land in
the slots marked ⟨RESEARCH⟩. What is written here are the decisions the repository has already made
and must not casually unmake.

---

## 0. The rule this plan is subordinate to

The product's claim is not "we answer legal questions". It is **"the model explains, the code
decides, the record verifies."** Every architectural choice below is judged against whether it keeps
that true under load, under cost pressure, and under a customer asking for a faster answer.

Three existing mechanisms enforce it and are **not up for renegotiation**:

| Mechanism | File | What it forbids |
|---|---|---|
| The ring firewall | `checker/rings.py` | Ring 0 cannot import ML. A prediction can never become a legal determination by accident. 36/36 tests, including transitive and dynamic imports. |
| The admission gate | `checker/admission.py` | Nothing is servable until `production_usable` is true. Today that is **one** instrument. |
| The calibration contract | `checker/calibration_contract.py` | No probability is shown to a user until its calibration is measured. |

A feature that needs one of these relaxed is not a feature; it is a different product.

---

## 1. What already exists, so we build on it rather than beside it

- **`backend/budget.py`** — runtime budget enforcement before every model call. Already has a
  `PRICING` table, `cost_inr()` with batch discount, a `Verdict` (allowed / mode / reason /
  spent_today / spent_month), a `Store` **Protocol** with a `FileStore` implementation, and three
  modes: `normal · budget · offline`.
  Two of its design rules carry into everything below:
  - **"A budget guard must only ever be wrong in the expensive direction."** It deliberately encodes
    list price, not the discount we currently receive, because a guard that under-estimates silently
    starts admitting calls it should refuse the day a promotion ends.
  - **Exhaustion is not an error.** The product degrades to template mode and says so. Never a
    silent failure, never a guess.
- **`checker/mcp/`** — thirteen read-only tools, `_policy` and `_boundary` on every response, no
  write of any kind. Structurally a BYOMCP server (see `docs/research/CONNECTORS_AND_THE_WHITE_SPACE_2026_09_25.md`).
- **`checker/operations.py`** — a watchlist can trigger an operation; operations create four task
  types; `EvidenceBudget` is a named count, not a score.
- **`scripts/serve_ask.py`** — the demo server, loopback only, refusing uploads by field name.

`budget.py`'s `Store` Protocol is the seam. Per-tenant metering is an implementation of it, not a
rewrite.

---

## 2. Tokens — the questions, and which are already answered

| Question the founder asked | Status |
|---|---|
| How many tokens should we use per user? | ⟨RESEARCH⟩ — needs the worked cost model |
| Where are tokens stored? | **Decided in shape**: `Store` Protocol. `FileStore` today; Postgres/Redis behind the same interface. The logic does not change. |
| What does "unlimited" mean? | ⟨RESEARCH⟩ — but see §2.1: it cannot mean unmetered |
| Rate limiting | ⟨RESEARCH⟩ for algorithm; **decided** that a refusal must be a stated mode, not a 500 |
| How long a context can we handle? | ⟨RESEARCH⟩ — and note the correctness hazard in §2.2 |

### 2.1 "Unlimited" is a pricing word, not an architecture word
Whatever is sold, the backend meters. The reason is not commercial, it is evidential: a bill a
customer disputes must be explainable **per user action** — one document check, one summary — not
per raw API call. That means the usage event is keyed to the action, and the model calls hang off
it. Designing it the other way round makes the bill unexplainable and the cost unattributable.

### 2.2 Caching has a correctness hazard specific to us
A result cache keyed on document hash is the obvious win and it is **dangerous here**: the same
document, asked the same question, has a *different correct answer* after the law changes. Any cache
key must include the **law version** (`checker/currency.py`'s as-of), or we will serve a confident
answer about superseded law — the exact failure the product exists to prevent, arriving through an
optimisation. ⟨RESEARCH⟩ fills in the rest of the caching strategy; this constraint binds it.

---

## 3. The funnel — how a customer's data gets in

The founder's model is Harvey's: the user connects their systems and works inside our workspace.
Research already settled the hard part, and the answer is uncomfortable:

- **MCA21 has no OAuth, no delegation and no API.** A customer *cannot* connect their MCA account.
  The only documented lawful inbound route for filing data is **customer-in-the-loop upload** — they
  fetch the document from MCA21 themselves and give it to us.
- Document systems (Microsoft Graph, Google Workspace, iManage, NetDocuments, DocuSign) *are*
  connectable by OAuth, and Graph is first by install base among Indian CS and in-house teams.

**This forces a decision the prototype has so far avoided.** `serve_ask.py` refuses uploads by field
name, deliberately and well. But if customer-in-the-loop upload is the only lawful path for filing
data, then a vault is not a feature we might add — it is the only inbound door that exists. The
refusal was right for a demo with no storage story; it cannot survive contact with a real customer.

What a vault obliges us to build, none of which exists today: per-tenant isolation and encryption,
retention and deletion, an audit trail, and a DPDP position on sending a client's document to a
US-hosted model. ⟨RESEARCH⟩ on all four.

---

## 4. The dashboard — what it may show

Constrained by the admission gate, not by design taste. A dashboard may show an obligation only if
its instrument is `production_usable`. **Today that is one instrument**, and the honest dashboard is
correspondingly small.

⟨RESEARCH⟩ supplies the real Companies Act compliance calendar — obligation, section, trigger,
deadline rule, form, consequence. Two design rules already apply to it:

1. **A deadline is computed, not stored.** "Within 30 days of the AGM" is a rule; the date is
   derived from a fact the customer supplied, and the derivation must be shown.
2. **An obligation we cannot decide must read as undetermined, never as compliant.** D3's finding —
   an invented `company_class` silently deciding s.2(85) — is the shape of this failure, and it
   reached a card that said nothing was decided.

---

## 5. Open questions this plan must close before any feature is built

1. Vault or no vault — and if yes, the DPDP and confidentiality position, in writing.
2. The context strategy: retrieval, long-context, or hybrid, decided on measured cost and measured
   accuracy rather than on preference.
3. Where the model call lives: request path, queue, or batch — and the latency a lawyer tolerates.
4. What "unlimited" is sold as, and what the meter does underneath.
5. Whether the MCP server becomes a distribution channel (OAuth 2.1 + PKCE, remote transport) before
   or after the first paying customer.

Nothing in §5 is a coding task yet. Each is a decision with a cost attached, and the research
running now is what attaches the costs.


---

# Part II — the research, and what it decides (26-09-2026)

Two of three streams returned. Full reports: token/context economics and vault/verification. The
compliance + DPDP stream is still running; §4's obligation table stays ⟨RESEARCH⟩.

**One claim from the research was checked and is false.** The vault report asserted "A CIN has a
check digit. Nothing in Harvey, Spellbook, ChatGPT or Claude computes it." There is **no published
check digit for a CIN** — the last six characters are the ROC serial number, and the format is
listing status + NIC industry + state + year + class + serial, with no checksum. It was the most
actionable-sounding line in the report and building on it would have meant implementing a validator
that cannot exist. Recorded because the report is otherwise excellent, and an excellent report is
exactly the kind that gets believed without checking.

The underlying argument survives intact and is better without it: what caught the corrupted CIN was
**internal consistency** — `+97` is not India's country code, and the same document prints `146323`
elsewhere. That mechanism is already built (`eval/prelabel/compare.py`, the "document against
itself" column) and it is the row of the table we can actually occupy.

## 5. Tokens — the questions, answered

### 5.1 The single highest-leverage decision is caching, not model choice

At 100 document-checks/month, per user, INR at 96/USD:

| Model | Cached prefix | No cache |
|---|---:|---:|
| Opus 5 | ₹2,386 | ₹4,632 |
| Opus 5.5 | ₹1,809 | ₹3,706 |
| **Sonnet 5** | **₹954** | ₹1,853 |
| Haiku 4.5 | ₹401 | ₹746 |

At a plausible Indian mid-market seat of ₹5,000–₹10,000/month, **Sonnet 5 cached leaves 80–90% gross
margin; Opus 5 uncached leaves almost none.** The statutory prefix is the same on every call and it
is the whole cost. Whether it actually hits cache is worth more than which model runs.

**Caching is also a throughput multiplier, not only a price cut.** `cache_read_input_tokens` do not
count toward input-tokens-per-minute limits on current Claude models. An 80% hit rate turns a 2M
ITPM ceiling into an effective 10M.

### 5.2 Four counters, not two

A usage event must record `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`
and `output_tokens` separately. `input_tokens` counts **only the tokens after the last cache
breakpoint** — treating it as total input under-bills by up to 90%. `backend/budget.py`'s
`cost_inr()` takes two integers today; it needs four.

### 5.3 The 429 that must never be retried

Anthropic returns `rate_limit_error` for two different things:

| Signal | Meaning | Response |
|---|---|---|
| 429 **with** `retry-after` | ordinary rate limit | back off exactly that long |
| 429, **no** `retry-after`, `error.details.error_code == "enforced_spend_limit_reached"` | monthly spend cap | **stop. Retrying always fails**, including the SDK's automatic retries. Fall to `budget`/`offline`. Access returns 00:00 UTC on the 1st. |

`budget.py` currently has no notion of this distinction. Treating them alike burns the retry budget
against a wall for the rest of the month. **This is the first code change Part II implies.**

### 5.4 `reserve` / `settle`, because a guard that only records cannot refuse

Cost is unknown until the call returns. A guard that records afterwards enforces nothing — which
contradicts `budget.py`'s own rule that it must only ever be wrong in the expensive direction. So
the `Store` Protocol gains a reservation at the **worst case**:

```
reserved = count_tokens(request) × input_price  +  max_tokens × output_price
```

then `settle` releases the difference. Set `max_tokens` to a realistic ceiling per action type —
`max_tokens` does not count toward rate limits, but it does size the reservation.

### 5.5 A tokenizer change is a ~30% price rise that no price table shows

Claude 4.7+ models (Opus 5/5.5, Sonnet 5, Fable 5.x) use a tokenizer producing **~30% more tokens
for the same text** than Sonnet 4.6 / Haiku 4.5. So `PRICING` is half a cost model: it needs a
**tokens-per-page constant per model** beside it, or every estimate for a 4.7+ model is 30% low.
This is the same failure shape as encoding a promotional discount.

### 5.6 Usable context is ~32K, not 1M — and our text is the worst case

Every independent benchmark puts the knee far below the advertised window. NoLiMa: 11 of 12 models
below half their short-context baseline **at 32K**. Chroma's Context Rot across 18 models: a single
distractor degrades performance, four compound it — **and models do worse when the haystack has
logical flow.** Shuffling it *improved* results in all 18.

Statutory text and diligence bundles are maximally coherent: same drafting style, same defined terms,
repeated near-identical clauses. **We are the worst case for long context, not an average one.** Size
chunking against ~32K. And note: no long-context benchmark covers Indian statutory drafting —
provisos, explanations, non-obstante clauses — so we should expect worse than published figures, not
better.

### 5.7 Long context is an accuracy purchase, never a cost saving

Per question against a 300-page bundle, Opus 5, prefix cached both ways: stuffing ₹16.55/question
against cached RAG ₹10.20, and stuffing additionally pays a ₹207 cache write. Cached RAG wins at
every N. Two free wins from the literature:

- **Order retrieved chunks by position in the source document, not by relevance score.** NVIDIA's
  OP-RAG: 16K retrieved tokens scored **F1 44.43** against **34.32 for the full 128K context**.
  Quality against chunk count is an inverted U — more retrieval eventually hurts.
- **Self-Route**: one cheap call decides "can I answer from these chunks?", escalating only on no.
  That maps exactly onto the existing `normal · budget · offline` ladder.

### 5.8 Gemini has a cliff Claude does not

Crossing 200k input re-rates the **entire** Gemini 3.1 Pro request ($2→$4 in, $12→$18 out). A 33%
larger input more than doubles the bill. Claude bills a 900k request at the same rate as a 9k one.
For our shape of work that difference is decisive, and it is an argument against a
lowest-price-per-token comparison.

## 6. The answer cache, and the only data model that survives a retrospective amendment

§2.2 said the cache key must carry the law version. The research sharpens it into something
buildable, and into a warning.

**The key is the provenance actually used, not a global corpus version:**

```
answer_key = H(document) · H(question) · prompt_version · model+params · H(law_state_vector)
```

where `law_state_vector` is the set of `(instrument, section, version)` that answer actually relied
on. A global `corpus_version` counter would mean any amendment anywhere invalidates every cached
answer, and with Indian instruments amended continuously the hit rate collapses to zero — the cache
stops existing. Keying on the document alone serves pre-amendment answers forever.

**This imposes a retrieval obligation:** every chunk must carry `(instrument, section, version,
in_force_from, in_force_to)`, and each answer must persist the union of provenance used. **A
retriever that does not emit provenance makes a safe answer cache impossible.**

**Retrospective amendment breaks ordinary caching entirely.** It changes the right answer for dates
already past, and the stale answer is already in a client's file. Three consequences:

1. **Lazy expiry is unacceptable.** Purge must be eager, triggered by ingesting the amending
   instrument — not by a read.
2. **Purge is necessary but insufficient; we need recall.** "Which tenants received which answers
   relying on s.X between dates A and B" must be answerable, which makes the answer log a queryable
   first-class table indexed by provenance — not a cache detail. The invalidation event is a
   **notification workflow**, not a `DEL`.
3. **Bitemporal or nothing.** `valid_time` (when the provision is in force — **rewritten by a
   retrospective amendment, including into the past**) and `transaction_time` (when we learned it —
   **append-only, never rewritten**). Without the second axis we cannot distinguish *"we were
   wrong"* from *"the law changed"* — and in a legal product **that distinction is the entire
   liability position.**

The practical rule: **make the answer cache a memo of a computation, not a store of a conclusion.**
A hit whose provenance versions have moved is a miss **plus an alert**.

No named production system doing statute-version-keyed answer caching was found. This is assembled
from CDN cache-tagging (surrogate keys / cache tags, purge-by-tag) and bitemporal practice, and is
flagged as synthesis rather than precedent.

## 7. What the vault research decides

### 7.1 Harvey's "100,000 files" is storage, not query scope

100,000 stored per vault; **~10,000 queryable per thread**; Harvey's own engineering post puts the
Vault working set at 1,000–10,000. Conflating the two is the common misreading. An IVF-PQ index
tuned for sub-2s P50 cannot be exhaustively scanned per query — the working set is necessarily
bounded.

### 7.2 We are ahead of Harvey on one thing, and it is our thing

Harvey's public citation schema is `{citation_num, document_name, page (nullable), text}` — **page
granularity plus a verbatim snippet, no character offsets, no bounding boxes.** Anyone wanting
"click the citation, jump to the highlighted span" does their own client-side text match, which can
land on the wrong instance when OCR text and rendered glyphs disagree.

D4's tracer already verifies `char_location` offsets and requires `source.text[start:end]` to be
**byte-identical** to the quoted text. That is a stricter anchor than the market leader publishes.

### 7.3 The mechanisms that are decisive when they fail are absent everywhere

| Mechanism | Decisive on failure? | Present in Harvey / Spellbook / ChatGPT / Claude |
|---|---|---|
| Signature validation | yes | no |
| Hash against an authoritative copy | yes | no |
| Lookup against a register | yes | **no** |
| Cross-field internal consistency | yes | **no** — *we have this* |
| Two models agreeing | **no** — correlated failure | relied on implicitly |
| Self-reported confidence | no — uncalibrated | not published |
| Citation to source | **no** — proves retrieval, not truth | yes, universally |

**Provenance and truth are orthogonal.** Harvey's Verbatim column preserves the exact wording *of
the extracted text layer*. If that layer says `7`, the verbatim quote says `7`, the citation resolves
to the right page, and every provenance check passes while the fact is wrong. That is our SD-006,
described from the outside.

### 7.4 Document *sets* are the weakest area in the whole market

No vendor publishes near-duplicate detection, version-lineage reconstruction, executed-versus-draft
determination, or conflict resolution across a bundle. This is structural, not an oversight: agentic
top-k retrieval returns passages ranked by relevance, and seven versions of the same clause are seven
near-identical high-scoring passages. **Nothing in a relevance ranking can tell you which one was
signed.** Answering "which is operative" needs document-level lineage carried *outside* the vector
index.

### 7.5 Take vendor accuracy figures apart before quoting them

Harvey publishes 96–99.7% on one-click workflows. The metric is **recall** — did it find the thing.
**No precision figure is published**, and a system that over-extracts scores beautifully on recall
while being dangerous in diligence. Independent numbers are far lower and measure harder things:
Vals' lawyer-controlled benchmark puts data extraction at 75.1% (lawyers 71.1%); ContractEval puts
frontier models at **F1 ≈ 0.64** on CUAD clause extraction, with **near-zero scores on rare
categories like Uncapped Liability** while Governing Law exceeds 0.9 — aggregate accuracy hides
which fields are worthless.

Two findings to design against: models falsely answer **"no related clause"** when one exists (up to
30.6% on one model) — a silent false negative, the worst failure in diligence; and **thinking mode
reduced F1** while improving Jaccard.

**No benchmark in the field measures document sets, OCR fidelity, abstention or calibration.** A
corrupted glyph is invisible to every one of them.

### 7.6 "Astra Legal" is real, and it is OpenAI's

**Astra for Law**, released 17-09-2026 — GPT-6 Astra plus a legal search index over CourtListener
(230M+ URLs), not a new model and **not a vault**. Scores 54.0% on Vals' Legal Research Bench against
38.7% for the web-search baseline. Reported as a 40% relative gain; read absolutely, **nearly half
its answers fail the correctness check**, and its answers are ~2× longer, which flatters
recall-flavoured rubrics. No third party has re-run it.

Note for India: **astrealegal.com is an Indian law firm**, not a vendor. Easy to conflate.

## 8. What Part II changes in the build order

1. **`budget.py` gains the spend-cap 429 distinction.** Small, and it prevents a month-long retry
   storm. First code change.
2. **Four token counters, and tokens-per-page per model.** Without them the meter is wrong by up to
   90% and every 4.7+ estimate is 30% low.
3. **`reserve`/`settle` on the `Store` Protocol.** The guard cannot refuse without it.
4. **Chunks must carry `(instrument, section, version, in_force_from, in_force_to)`.** This is the
   precondition for a safe answer cache, and it is retrieval work, not cache work.
5. **Bitemporal statutory facts.** Not deferrable — it is the liability position, and retrofitting a
   second time axis after answers exist is much harder than starting with it.
6. Order retrieved chunks by source position; implement Self-Route onto the existing mode ladder.


---

# Part III — compliance, DPDP, and a repo belief that has gone stale (26-09-2026)

The third stream returned. It read primary sources: the India Code consolidated Act with amendment
footnotes, SEBI LODR as amended to 22-01-2026, SEBI circular 185 of 31-12-2024, and the CERT-In
s.70B directions. Rule-level items (forms, thresholds in subordinate legislation) are mostly
secondary and it says so — **no [I]-tagged rule-level deadline enters the corpus without the G.S.R.**

## 9. A verified correction to CLAUDE.md, found while checking the report's method

The report cited `www.indiacode.nic.in`. `CLAUDE.md` states that host "403s everything", that the
live host is `indiacode.gov.in`, and that "any hardcoded `.nic.in` URL is dead". **Measured today,
that is false, and the truth is worse than merely being out of date:**

| URL | Content-Type | Result |
|---|---|---|
| `www.indiacode.nic.in/bitstream/123456789/2114/5/A2013-18.pdf` | `application/pdf` | **200, 3.2 MB, a real 370-page Companies Act 2013** — parsed by our own reader, contains s.2(85) |
| `indiacode.gov.in/bitstream/123456789/2114/5/A2013-18.pdf` | `text/html` | **200, 6.7 KB — the DSpace Angular shell.** A soft-404. |

Two consequences, and the second is the dangerous one:

1. The `.nic.in` host is **not** dead for bitstream paths. `checker/provenance.py:55` excludes it "on
   purpose: it is dead", so our permitted-host list currently refuses a host that serves the
   authoritative file.
2. **`indiacode.gov.in` returns HTTP 200 with an HTML page for bitstream paths.** Any fetcher that
   checks only the status code gets an Angular shell where it believes it has a PDF. That is the
   silent-failure class this repository exists to refuse, sitting in the one host we do permit.

**Buildable requirement:** the fetch path must assert `Content-Type` and magic bytes, not status
code. A 200 that is not `application/pdf` starting `%PDF` is a failure, and must be recorded as one.
The REST API (`indiacode.gov.in/server/api`) is unaffected and remains correct.

## 10. The three findings that change what we build

### 10.1 DIR-3 KYC stopped being annual, and nobody's calendar knows

G.S.R. 943(E) of 31-12-2025, w.e.f. **31-03-2026**, replaced annual director KYC with a **triennial**
filing due 30 June of every third financial year. Directors current at the changeover are next due
**30 June 2028**. *Every compliance calendar published before 2026 says "30 September, annually" and
is now wrong.*

**This is the demo.** It is a live, checkable, recent instance of exactly the failure the product
exists to catch, in a filing every company secretary knows. It is worth more than any synthetic
example — and note we removed "DIR-3 KYC" from the website copy last week because no such obligation
row exists in the register. Building the row is now the highest-value single obligation we could add.
Pull the gazette before shipping it; the finding is secondary-sourced.

### 10.2 G.S.R. 880(E) consumed all the statutory headroom

The small-company thresholds now sit at **₹10 cr paid-up / ₹100 cr turnover** — which are the Act's
own ceilings in s.2(85) ("not more than ten crore", "not more than one hundred crore"). **The rule
has used up all available room; the next expansion needs an amending Act, not a rule.**

The consequence is not cosmetic. A large population became "small" on 01-12-2025 and thereby dropped
from **4 board meetings with a 120-day maximum gap to 2 meetings with a 90-day gap** (s.173(5)), and
from MGT-7 to MGT-7A. Applying today's threshold to an FY2024-25 document produces exactly the wrong
answer — and 880(E) is already the instrument our provenance chain holds and serves.

### 10.3 Applicability has had five answers, and that is the product

"Is this a small company?" changed on **13-02-2015, 09-02-2018, 01-04-2021, 15-09-2022 and
01-12-2025.** The same pattern holds for the s.135 CSR test period (19-09-2018), the s.177 net
(07-05-2018), the s.204 loan limb (FYs from 01-04-2020) and DIR-3 KYC's entire periodicity
(31-03-2026).

**So the data model is `applicable(company_facts, obligation, as_at_date) -> decision + the
instrument version relied on` — never a boolean stored against a company record.** That sentence is
the architecture. A stored flag is wrong the moment a rule moves, and wrong silently.

## 11. DPDP — the honest answer, which is not the expected one

**As of today, essentially no DPDP obligation binds a data fiduciary.** ss.3–17 of the Act and Rules
3, 5–16 commence **13 May 2027**. The law actually governing a client document sent to a US endpoint
today is still **IT Act s.43A + the SPDI Rules 2011**, under which transfer is lawful on a
consent-plus-contract basis with **no country whitelist and no approval step**.

From 13-05-2027 the test becomes s.16 + Rule 15 — and DPDP is **blacklist**, not adequacy: transfer
is permitted by default and becomes unlawful only to a country the Government notifies. No country
has been notified.

**So a US endpoint is lawful now and probably lawful in 2027.** The risks that are real are
different from the ones usually cited:

- **Rule 13(4)** lets the Government bar offshore transfer of specified categories for a Significant
  Data Fiduciary — a blank cheque not yet filled in. Buildable requirement: a per-tenant **"no data
  leaves India" mode that is a real deployment**, not a setting that still calls a US endpoint.
- **CERT-In's 180-day log retention is in force now** and is a localisation requirement today.
- **Professional confidentiality is where an Indian CS or advocate will actually push back**, and it
  is not a data-protection question at all. A board resolution or shareholders' agreement is mostly
  *corporate* information; a DPDP analysis does not answer the confidentiality objection and must not
  be allowed to stand in for one.

### 11.1 "India region" almost never means in-region inference

| Provider | Reality |
|---|---|
| **AWS Bedrock** ap-south-1/2 | Current Claude models are reached via **Global cross-region inference — requests from Mumbai/Hyderabad route to AWS commercial Regions, i.e. inference leaves India.** Logs stay in-region; inference does not. |
| **Anthropic first-party** | No India region. US/EU/CH/AU. |
| **Azure OpenAI** | Central/South/West India regions; the strongest residency story — **verify per model**, since new models land in India late or not at all. |
| **Google Vertex** | asia-south1/2 with real residency control, but a thin in-region model catalogue. |
| **OpenAI** | India residency reported as **at-rest only, with inference still on US infrastructure** — which would not satisfy a Rule 13(4)-style obligation. Unverified; confirm with OpenAI directly. |

**The pattern: "India region" is data-at-rest residency, not frontier-model inference in India.** A
promise that documents never leave India currently costs either an older in-region model, Azure
OpenAI with per-model verification, or self-hosting open weights. That segment — listed companies,
PSUs, banks — is disproportionately the one that pays most.

## 12. The three constraints that bind hardest

1. **The "in force at date D" lookup must reach circulars, not only Acts and Rules.** SEBI reg.
   27(2)(a) now contains **no timeline at all** — it says "as specified by the Board from time to
   time", and the 30-day figure lives in a December 2024 circular. MCA's CCFS-2026 relief existed
   only between 15-04-2026 and 31-08-2026. An engine admitting only statutes silently produces "no
   deadline" or the wrong one.
2. **Applicability is a computed, dated predicate** (§10.3).
3. **Almost every annual deadline hangs off one stored event — the actual AGM date — and the fallback
   when it is absent is worded differently in s.92(4) and s.137(2).** Store `agm_actual` and
   `agm_due` separately; derive MGT-7 (60d), AOC-4 (30d), ADT-1 (15d) from the pivot; handle the
   Registrar's 3-month extension (unavailable for a first AGM) and the OPC carve-out (AOC-4 at 180
   days from FY close, no AGM at all). Getting this wrong is wrong for every company, every year.
