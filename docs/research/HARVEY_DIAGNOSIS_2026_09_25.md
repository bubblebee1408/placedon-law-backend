# Harvey, and where PlacedOn actually stands against it — 25 Sep 2026

Desk research from public sources. **No claim here is verified by us**, and the pricing figures are
third-party reports Harvey has not confirmed. Sources at the end.

## 1. What Harvey is, as a product

Five surfaces:

| Surface | What it does |
|---|---|
| **Assistant** | Ask, upload documents, draft. Answers grounded in the supplied documents and legal sources. |
| **Vault** | Secure document store, **up to 100,000 files per vault**, bulk analysis, syncs with iManage, SharePoint, Google Drive. |
| **Workflows** | Multi-step matter automation, built in natural language or a visual builder, no code. |
| **Knowledge** | Research across **500+ curated sources / 90+ jurisdictions**, including LexisNexis, Wolters Kluwer, **SCC Online**. |
| **Harvey for Word** | Inline edits inside Word. |

**How it works.** Legal fine-tuning plus RAG, and an agent that iterates: retrieves authority,
follows citations and distinctions, checks its work against the prompt, returns inline citations.
It extracts the citation graph across its case-law corpus — which case cites which, and how it is
treated. Verification steps check cited cases and statutes against actual legal databases.

**Reported pricing** (none confirmed by Harvey): ~**$1,200/seat/month**, ~$2,400 bundled with
LexisNexis; **20–25 seat minimum**, 12-month term ⇒ roughly **$288k–$360k/year** entry. Renewal
increases of 10–25% reported.

## 2. The uncomfortable part: Harvey is already in India

- **Bengaluru office** open.
- Indian clients reported: **AZB & Partners, Shardul Amarchand Mangaldas & Co, S&A Law Offices** —
  i.e. the top of the market.
- **India integrated as a national source.**

Any plan that assumed "Harvey is not here yet" is out of date. They are here, and they arrived at
the firms that can pay $300k a year.

## 3. The gap that is genuinely still open — and it is ours

**Harvey's own writing does not claim point-in-time statutory research.** Their article on what the
agent changes about legal research does not address as-of-date research at all. What they describe
as coming is **precedential treatment** — a warning when a case was overturned on appeal, checked at
runtime against your specific claim. That is **case law**, and it is **upcoming, not shipped**.

Nobody credible is claiming *"the statute as it stood on 14 August 2025"* for Indian law.

**And the failure it prevents is measured.** A 60-case audit on the Indian Contract Act 1872
(arXiv:2608.21089) introduced a **High-Confidence Error Rate** — wrong answers delivered at ≥9/10
confidence — and found frontier models fail specifically on **modern statutory shifts**:

| Model | High-Confidence Error Rate |
|---|---|
| Meta AI | **31.7%** |
| Perplexity AI | 15.0% |
| ChatGPT (GPT-5.2) | 6.7% |

The named failure is the **2018 amendments to the Specific Relief Act**: models applied
**pre-amendment rules while asserting near-perfect confidence**. That is PlacedOn's thesis with a
number attached, from someone else's measurement.

## 4. The competitor that should worry us more than Harvey

**Vaquill** serves an India legislation API at a scale we are nowhere near:

| | Vaquill | PlacedOn |
|---|---|---|
| Acts | **64,179** served live | 1 (Companies Act 2013) |
| Sections | **745,970** individually addressable | **529** ingested |
| Official publisher link | 89.3% of acts (57,316) | every registered instrument |
| Amendment events held | **1,061 of 1,901** acts that claim one (55.8%) | full amendment parser on one Act |
| **Point-in-time (`asOf`)** | **"There is no asOf on this API"** — unavailable "until this corpus is versioned" | boundary behaviour **proved on s.177, s.447, s.35**, 6/6 boundaries |

Read that last row twice. The largest Indian-statute API **explicitly does not have the feature we
are building**, and says so in its own documentation. They also refuse to fold amendments into
source text — *"we serve the publisher's text as published, and never rewrite it"* — which is the
same discipline as ours.

So the moat is real and unclaimed. But we are defending it with **529 sections against 745,970**,
and our point-in-time is proved on **three sections, six boundaries** — not on a corpus.

## 5. What this means for what we build

**Do not try to be Harvey.** Vault, Workflows, Knowledge across 90 jurisdictions and a Word editor
are years and a sales force away, and they are already sold to the firms that would buy them.

**Be the thing Harvey's architecture cannot answer.** Harvey grounds an answer in *a* source. It
does not establish that the source is *the law that applied on the date of your document*. That is
a different question, and it is the one that produces a 31.7% high-confidence error rate elsewhere.

Ranked by defensibility per unit of work:

1. **As-of-date statutory answers, with the instrument and in-force date on the face of every
   figure.** Already built for the Companies Act. This is the only thing we have that neither
   Harvey nor Vaquill claims.
2. **Abstention as a first-class product state.** We refuse and say why. Harvey's public material
   is about grounding answers, not about declining to answer. Our demo already refuses an ICSI
   specimen for having no date on its face.
3. **The audit layer on a filed document** — is this the right document type, for this company, on
   this date, against the law then in force. Harvey analyses documents; it does not adjudicate
   them against a dated statutory register.
4. **Provenance that survives an audit** — Gazette-hashed instruments, re-read on the serving path.
   SD-006 (a filing whose letterhead encodes `1` as `7`, corrupting a CIN, which *both* models read
   faithfully) is the argument for this, and it is ours, measured.

**What to stop claiming.** MCA21 connection, drafting in Word, practice packs, MCP-as-inbound —
all four are now corrected on the local frontend branch, because Harvey *does* have the real
versions of several of them and a side-by-side would have been embarrassing as well as untrue.

## 6. Honest scoreboard

| | Harvey | PlacedOn today |
|---|---|---|
| Jurisdictions | 90+ | 1 body of law, 8 more declared-and-refused |
| Document store | 100k files/vault, DMS sync | none; no upload by design |
| Drafting | inline in Word | one template, wired to nothing |
| Human expert validation | firm-deployed at AZB, SAM | **none — zero obligations reviewed by a CS** |
| Accuracy benchmark | third-party tests exist | **never benchmarked** |
| Point-in-time statute | not claimed | **built, proved on 3 sections** |
| Abstention as a state | not a stated product feature | built and tested |
| Price | ~$288k–$360k/yr entry | — |

The one row we win is row six. Everything else is a gap, and the row that should frighten us most
is **human expert validation**, where we are at zero and they are deployed inside the firms whose
partners would tell us we are wrong.

## Sources
- https://www.harvey.ai/ · https://www.harvey.ai/blog/what-the-harvey-agent-changes-about-legal-research
- https://www.harvey.ai/blog/100-knowledge-sources-available-in-harvey · https://www.harvey.ai/blog/harvey-expands-global-data-coverage
- https://law.asia/harveys-passage-to-india/ · https://www.legaltechnologyhub.com/vendors/harvey/
- https://lawyerist.com/reviews/artificial-intelligence-in-law-firms/harvey-ai-review-artificial-intelligence-for-lawyers/
- https://claudeforlawyers.com/blog/harvey-ai-pricing · https://thelegalprompts.com/blog/harvey-ai-pricing
- https://www.vaquill.ai/in
- arXiv:2608.21089 — "Can Legal AI Know When It Is Wrong? And Do Students Know When It Is?"
- arXiv:2405.20362 — Stanford RegLab, "Hallucination-Free?" (17–33% hallucination in legal AI)
