# Spellbook: business model, and what its features require underneath

## What this document is, and what it refuses to be

Every claim here is derived from a publicly stated feature by asking: *given that
this feature works as described, what must be true beneath it?* That is
engineering inference and it is falsifiable — if a claim is wrong, a demo or a
support answer will show it.

**Nothing here is knowledge of their code.** No account was used, no
authenticated area accessed, no internals observed. Where a design is genuinely
underdetermined, this says so rather than picking the plausible one.

That restraint has a specific reason. `COMPETITOR_PATTERN_ANALYSIS.md` in this
repository examined an unsourced document describing a competitor's internals in
confident detail and classified its central claim as likely fabricated on seven
markers — the sharpest being that **real pipelines are named after the failures
that produced them, and invented ones read like a textbook**. A "simulation" of
Spellbook's architecture would produce exactly that artifact and it would be
quoted back as intelligence six months later.

Confidence is marked throughout:

    NECESSARY   the feature cannot work without this
    LIKELY      strongly implied; a competent team would almost certainly do it
    OPEN        genuinely underdetermined from outside; do not guess

---

## 1. Business model, from public signals

**Pricing is not published.** The page says *"flexible pricing for teams of all
sizes"* and *"pricing is determined by the number of team members on a
licence"*. To get a number you must start a 7-day trial or book a demo.

What that combination indicates:

| Signal | Reading |
|---|---|
| Per-seat, not per-matter or per-document | Revenue scales with headcount, not usage. Predictable for them, and it means a small firm pays per lawyer whether or not they use it. |
| No public price | Sales-led. Price is discovered per account, which usually means it varies, and varies with negotiation. |
| 7-day self-serve trial | A product-led top of funnel feeding a sales-led close. They want you inside before the price conversation. |
| "Dedicated support for teams over 10 members" | Ten seats is where they start investing. Below that you are self-serve. |
| In-house tier gets a "Playbook Build Service" | **Services revenue attached to the product**, and a strong retention mechanism — a customer who has paid to encode their playbook has a switching cost the software alone does not create. |

**The structural read:** the playbook is the lock-in, not the model. Anyone can
rent the same LLM. Nobody else has your encoded standards. That is the same
insight behind Legora's "Lists" and Harvey's "Memory", and it is worth noting
because it is a moat available to a company with no proprietary model at all.

**What that costs a buyer in India, and why it matters to us:** per-seat pricing
set by negotiation with a sales team, on a product priced for North American
firms, is unlikely to reach a four-person practice in Pune. Not because the
product is bad but because the *model* is not aimed there. That is a gap in
their go-to-market, not in their engineering, and it is more durable than a
feature gap.

---

## 2. What each public feature requires underneath

### "Compare your contracts to thousands of similar agreements"

- **NECESSARY:** a corpus of agreements they hold, independent of the customer's
  own documents, and a retrieval method over it.
- **LIKELY:** dense-vector retrieval. Comparing to "similar" agreements is a
  similarity problem, and exact-match search does not answer it.
- **OPEN:** where the corpus comes from — public filings, licensed data,
  aggregated customer contracts under a licence term, or a mix. This matters
  enormously for a buyer and is not stated.

**Note for us:** this is the strongest argument that their architecture is
built around *similarity*, and it is a good fit for contracts, where "is this
clause unusual?" is a real question. It is a poor fit for statute, where the
question is "what did this provision say on that date?" — a lookup, not a
neighbour search, and one where a plausible neighbour is a wrong answer.

### "Encode your legal standards" (Playbooks)

- **NECESSARY:** customer-authored rules stored per tenant, and a comparison
  step that evaluates a clause against them.
- **OPEN:** whether that comparison is deterministic (a rule engine) or a model
  judging conformance. This is the single most interesting unknown about their
  system and cannot be settled from outside.

### "Answers you can trust, with citations" (Ask)

- **NECESSARY:** retrieval before generation, with document identity carried
  through to the output.
- **OPEN — and this is question 1 on our vendor list:** whether a citation
  resolves to an exact passage or to a document. Both are commonly called
  "citations". They are not the same product.
- **OPEN:** whether the cited text is *checked against* the answer, or merely
  retrieved alongside it. Retrieval proves relevance; it does not prove support.

### "Redline contracts... right in Word" (Review)

- **NECESSARY:** an Office add-in with access to the document object model, and
  a mapping from a proposed edit back to a character range in the document.
- **LIKELY:** the hard engineering here is not the model. It is producing a
  tracked change that survives Word's revision model without corrupting the
  document, and doing it on documents that arrive in every state Word permits.

### "Multi-document workflows" (Associate) and "end-to-end" (ACM)

- **NECESSARY:** orchestration across documents with state that outlives a
  single model call.
- **OPEN:** whether steps are a fixed graph or a model-chosen plan. The public
  language ("agent", "autonomous") suggests the latter, but marketing language
  is not architecture.

### Zero data retention, SOC 2, HIPAA, GDPR

- **NECESSARY:** provider agreements — which they state, naming OpenAI and
  Anthropic — plus tenant isolation and an audit trail to pass SOC 2.
- **Worth separating:** *"zero data retention with the LLM providers"* is a
  narrower claim than *"we do not train on your data"*. Their security page does
  not address the second. That is a gap in the page, not evidence of a practice.

---

## 3. What this architecture is not built to do

This is the section that matters for us, and it is inference from *problem
shape*, not from their code.

A contract-review system's ground truth is **the customer's own documents**.
That has properties statute does not:

| Contract | Indian statute |
|---|---|
| Exists in one version, the one signed | Exists in many versions, one per amendment |
| Has no commencement date | A provision can be notified and not in force |
| Nobody amends it retrospectively | Amending Acts change earlier text |
| No delegated instrument sets its thresholds | Operative figures often live in Rules |
| Private; the customer holds the truth | Public; the source is defective and known to be |

So a contract product has **no reason** to build amendment chains, commencement
provenance, or point-in-time reconstruction. Not because it would be hard — it
would be routine for a team of that size — but because its problem never asks
for it. Building it would add cost and answer no customer question.

**That is a prediction and it can be wrong.** If Spellbook applies the law as it
stood on a contract's signing date when answering about that contract, this
reasoning fails and our differentiation is smaller than we believe. Question 7
of `VENDOR_QUESTIONS.md` is written to find that out, and it should be asked
before we rely on any of this.

---

## 4. What we should take, and what we should not

**Take: the playbook as a retention mechanism.** Customer-encoded standards are
a moat available without a proprietary model. Our equivalent is not a clause
playbook — it is the company's obligation register and its accumulated evidence.

**Take: the trial-then-sales funnel.** Self-serve entry with a sales close fits a
product whose value is not obvious in a screenshot.

**Do not take: per-seat pricing.** It is calibrated to firms with many lawyers.
Our evidenced users are small practices and Company Secretaries.

**Do not take: similarity retrieval as the core.** It suits "is this clause
unusual?" and actively harms "what did this provision say on that date?" —
`checker/text_search.py` already argues this and the argument holds better
against a competitor's design than in the abstract.

---

## 5. How to falsify this document

Ask them. `VENDOR_QUESTIONS.md` holds eighteen questions, and four of them
resolve every OPEN marker above:

- Q1 settles whether citations are spans or documents.
- Q4 settles the missing-source behaviour.
- Q7 settles point-in-time law, and with it §3 of this document.
- Q10 settles whether anything deterministic checks the model.

Until those are answered, every OPEN above stays open. Filling one in from
imagination would convert this document into the kind of artifact it was written
to avoid.
