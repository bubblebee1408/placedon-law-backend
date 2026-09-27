# PLAN 20 — the product, for in-house legal teams

Written 27-09-2026. **Supersedes the customer decision in `docs/BUSINESS_PLAN.md`**, which names
practising Company Secretaries as primary and says in bold *"Not the buyer: large enterprises,
listed companies."* The founder has decided: **in-house legal teams first**, then law firms, then
individual lawyers. That document must be rewritten; this one records what replaces it.

Scope also widens: **corporate law**, not the Companies Act 2013 alone. In-house teams do M&A, due
diligence, NDAs, share transfers, board process. The Act is one input.

---

## 1. The one thing that is ours

Not the answer. **The record that the answer was right on the day it was given — and the ability to
find every answer that just became wrong.**

An in-house General Counsel's exposure is personal and retrospective. The question that ends careers
is not *"what is the law?"* It is *"you advised the board in March; the rule changed in June with
effect from April — what did you tell them, and on what basis?"*

Nobody sells the answer to that.

| | |
|---|---|
| **Harvey** | Its own article on its agent does not address as-of-date statutory research. What it promises is *precedential treatment* for overturned **case** law, and that is upcoming, not shipped. |
| **Vaquill** — the largest Indian-statute API, 64,179 acts / 745,970 sections | States in its own documentation: *"There is no asOf on this API"* — unavailable *"until this corpus is versioned."* |
| **Frontier models generally** | Measured **31.7% High-Confidence Error Rate** on modern Indian statutory shifts (arXiv:2608.21089, 60-case audit on the Contract Act) — wrong answers delivered at ≥9/10 confidence, applying pre-amendment rules. |

**"Palantir for lawyers" is the right framing and it is not a metaphor.** Palantir's value is not
analysis; it is that every fact carries where it came from and who saw it. Themis already has the
shape of that: the ring firewall, the admission gate, `observation_store` (append-only, bitemporal),
`event_log`, `currency.affected_by()`, and the glossary term the other session already wrote —
**"Recall (of advice): listing every answer that relied on a source later found wrong."**

**So the product is a legal position-of-record with a recall register.** Everything else — Q&A,
document check, summaries — is how positions get created. The recall is why a GC pays.

## 2. What that means we must NOT build

Stated so a future engineer does not add them back:

- **No fine-tuning of a legal model.** This is the biggest trap in the founder's reference material,
  whose Harvey diagram makes *"Layer 2: legal domain fine-tuning, 10B+ tokens"* the centre. Weights
  cannot be as-of-dated. A fine-tuned model knows what it absorbed and cannot say **when** it learned
  it, which is precisely the question this product exists to answer. `CLAUDE.md` already records the
  no-fine-tuning decision and logs training-data poisoning (E6) as latent *because* that path is
  dormant. We take the frontier model (Harvey's Layer 1) and the retrieval/vault/citation layer
  (Layer 3), and **deliberately refuse Layer 2**. That refusal is the product.
- **No case-outcome prediction.** Not calibratable on available Indian data. PLAN_19 §5.6 already
  refuses it; keep that.
- **No accuracy percentage** until a lawyer has checked a benchmark.
- **No "connected to your MCA filings".** MCA21 has no OAuth, no API and no delegation; there is no
  MCA-sanctioned aggregator licence to buy. The claim was deleted from the site for this reason.

## 3. What an in-house team actually needs, in order

The test for every row: *does an in-house counsel's week get measurably shorter or safer?*

| # | Capability | Why it is in this list | State today |
|---|---|---|---|
| 1 | **The vault** — they upload, it is theirs, isolated, retained, deletable, audited | MCA has no inbound path, so customer-in-the-loop upload is the **only lawful route** for their own documents. Without it there is no product for this buyer. | **nothing** |
| 2 | **Position of record** — every answer stored with its provenance, `as_of`, and `known_at` | This is §1. Half-built: `observation_store`, `event_log`. | partial |
| 3 | **Recall register** — "which positions relied on s.X, and who received them" | The thing a GC buys. Needs a reverse index over provenance. | **nothing** |
| 4 | **Change alerts** — an instrument lands, we name the affected positions | `currency.affected_by("880")` already returns affected obligation ids. Wire it to positions. | partial |
| 5 | **Document check** — is this the right document, for this company, on this date, against the law then in force | Built for public documents; needs the vault to matter. | built, narrow |
| 6 | **The compliance calendar** — computed deadlines, not stored dates | Deadlines are rules: "within 30 days of the AGM". Needs the AGM pivot and the threshold history. | **nothing** |
| 7 | **NDA / agreement review** against a playbook | What in-house teams do most. Clause extraction is a solved-ish problem; our edge is dating the statutory references inside it. | **nothing** |
| 8 | **Due-diligence bundle** — a document *set*, not a document | The weakest area in the whole market: no vendor publishes dedup, version lineage, or executed-copy determination. Relevance ranking cannot tell which of seven near-identical PDFs was signed. **This is an open gap, not a crowded one.** | **nothing** |

Rows 1–4 are the product. Rows 5–8 are why they open it daily.

## 4. Staging

**Stage A — in-house, mid-market Indian companies.** Deliberate, and the reason matters: Harvey is in
India, but its reported clients are **law firms** (AZB, Shardul Amarchand Mangaldas, S&A), and its
entry is ~20–25 seats at roughly $1,200/seat/month. **An Indian in-house team of three or four cannot
buy that.** So this segment is open — but we are selling *under* Harvey in a market they will descend
into, not in one they cannot reach. Speed matters.

**Stage B — law firms.** Only once a firm's per-matter isolation and ethical walls exist.

**Stage C — individual lawyers and CSs.** The original business plan's market. Cheapest to serve last,
because ₹3,000–6,000/year cannot fund the vault.

## 5. Pricing — the old numbers are void

`BUSINESS_PLAN.md` prices ₹3,000–6,000 **per year**, derived from 12,000 practising CS. At the
measured ₹2.91 per answer that supports ~86 answers a month, or **~26 document checks a month with
caching and 13 without.** For an in-house team that ceiling is absurd and the price is wrong.

Re-derive for in-house: a team of 3–5 lawyers at an Indian mid-market company buys software in the
**₹50,000–5,00,000/year** band. That is 10–100× the old figure and it is what funds rows 1–4.

**Caching stays existential, not cosmetic.** It doubles usable volume at any price, and the
measured-cheap default estimate found in verification (26.1% low) is a margin error, not a rounding
one.

## 6. What in-house buyers will demand that CSs never did

They are lawyers; diligence is their job. None of this exists yet:

- A **written DPDP position**. Today's operative law is still IT Act s.43A + the SPDI Rules; DPDP
  ss.3–17 and Rules 3, 5–16 commence **13 May 2027**. DPDP is blacklist, not adequacy, so a US
  endpoint is lawful now and probably then — but **Rule 13(4)** lets the Government bar offshore
  transfer of specified categories for a Significant Data Fiduciary, and **CERT-In's 180-day log rule
  is in force today**.
- A **confidentiality position**, which is *not* a data-protection question and is where an Indian
  in-house counsel will actually push back. A board resolution is corporate information, not personal
  data; DPDP does not answer it.
- **Residency.** "India region" almost always means data-at-rest, not inference. AWS Bedrock in
  Mumbai routes current Claude requests out of India. Azure OpenAI in an India region is the strongest
  story — verify per model.
- ISO 27001 / SOC 2 expectations, and a real per-tenant "no data leaves India" deployment rather than
  a setting that still calls a US endpoint.

## 7. Immediate order of work

1. **The vault** (row 1). Nothing else for this buyer works without it.
2. **Position of record + recall register** (rows 2–3), on the other session's
   `checker/observation_store.py`. **Not a second append-only store** — that is how two ledgers drift.
3. **Change alerts** (row 4), wiring `currency.affected_by` to stored positions.
4. **The DPDP and confidentiality position, in writing**, before the first customer conversation.
5. **Then** the calendar, NDA review, and diligence bundles.

Before any of it: the business plan's customer must be rewritten, and the ten founder conversations
its own risk table demands (*"Ten conversations before any further build"*) have not happened.
