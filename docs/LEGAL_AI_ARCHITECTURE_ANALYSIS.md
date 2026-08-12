# Deep law: what to build after the lattice

Written 2026-08-12, answering the Court Corridor and Deep Law Research prompts.

The strategic read in those prompts is right, and it is the best strategic thinking this project
has received: Harvey serves boardroom lawyers on desktop in English at $50,000/year, and cannot
reach a litigator on a phone in Nagpur. That gap is real and the lattice architecture happens to
suit it — conflict detection and provenance are litigation tools that arrived here disguised as
compliance features.

Two things in the Phase 1 build would do serious damage, and one research direction is more
important than anything else in the query set. Both below, then the sequence.

---

## 1. Two blockers in the Court Corridor MVP

### 1.1 The UI is asked to print a case citation we do not have

The spec says the conflict panel should read:

> ⚠️ Two provisions conflict. **Karnataka courts resolved this in X vs. Y (2024).**

We hold **zero judgments**. The corpus is 30 PoSH sections, 14 Rules, 4 MCA provisions, 31 District
Officers. Nothing else.

To render that sentence the UI must invent a case name, a court and a year — the single most
damaging output this product could produce. A wrong compliance date costs a customer a penalty. A
**fabricated case citation, shown to a litigator, carried into a filing**, ends the customer's
credibility with a judge and ours with the profession. It is also the exact failure Stanford
RegLab measured at 17–33% in Lexis and Westlaw, and the reason `verifier.py` exists.

`X vs. Y (2024)` is a placeholder in a design mock. In a compliance product a placeholder that
looks like a citation is a fabrication with a UI around it.

**What to show instead**, using only what we hold:

> ⚠️ **s.9 conflicts with its own proviso.** The section gives three months to complain; the
> proviso extends it. Both are quoted below. **No court has interpreted this in our corpus** —
> we hold statute only, no judgments.

That last clause is the differentiator. Every competitor's tool implies case-law coverage it does
not have. Saying "we hold statute only" is checkable, honest, and is the thing a litigator needs
to know before relying on it.

### 1.2 Charging ₹999/month for a product that abstains on everything

Measured, just now:

```
"Does Section 4 apply to a 5-employee startup?"  -> abstained (UNSUPPORTED)
"Is my POSH policy compliant?"                   -> abstained (UNSUPPORTED)
```

`verified_by` is null on all 30 sections. **The product currently answers nothing**, by design,
and that is correct — but it means a ₹999 subscription today buys a refusal, and ₹50 per analysis
buys a refusal per analysis. That is not a pricing strategy; it is a refund queue and a reputation
problem in a profession that talks to itself.

`bench_answers.py` measures what changes this: coverage goes **0% → 85%** after one evening of a
lawyer's time, with fabrication at 0%. **Gate 1 is not a nice-to-have before monetisation. It is
the thing that makes there be a product to charge for.**

Revenue sequencing that follows from the measurement:

| | When | Why |
|---|---|---|
| Free, honest, abstaining | now | The abstentions *are* the demo. Nobody else's tool says "no date is prescribed; here is who I asked." |
| ₹999/month | after Gate 1 | 85% coverage, 0% fabrication, measured |
| Per-analysis pricing | probably never | It prices the refusal, and the refusal is the most valuable output |

### 1.3 A smaller one: it would be the second frontend

The spec says "create app.py … Streamlit". A Next.js frontend already exists, is deployed, and now
fetches `/api/districts`. Adding Streamlit means two UIs, two deployments, and two places for the
district list to drift — the drift bug that was fixed three commits ago by deleting the second
list.

Mobile-first is the right instinct and the existing frontend is already responsive. The work is
CSS and a share button, not a new stack.

---

## 2. The research finding that outranks the rest of the query set

The prompt's Query Set B asks about trauma-informed AI. For **this** product that is not one
research direction among fifteen. It is the one with an ethical floor under it, because
**PoSH is a statute about harassment complainants.**

The moment this product is used by a woman deciding whether to complain — and it will be, because
"do I need an IC?" and "what if they fire me for complaining?" are the same search — it is a tool
touching someone in distress.

### What the literature says

- **[Designing Chatbots to Support Victims and Survivors of Domestic Abuse](https://arxiv.org/pdf/2402.17393)** —
  the design requirements paper to read first.
- **[Conceptualizations of LLM-Powered Chatbots in Sexual Assault and Domestic Violence Crisis Hotlines](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/pra2.1349)**
  (Wise, 2025) makes the point that matters here: *chatbots are indifferent to their outputs, but
  survivors in crisis require trauma-informed support*. Indifference is the default and must be
  designed against.
- **[AinoAid](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12817862/)** — needs assessment through
  usability testing, built with psychotherapists.
- Deployed systems: **OlimpIA** (Mexico, WhatsApp, 8,000+ cases, escalates to psychologists and
  legal experts), **HelloCass** (Australia), **Botler AI** (Montreal).

The recurring design finding across all of them: **the system must know when to stop being a
system.** Every credible deployment escalates to a human, and does so early.

### What follows for Placedon, concretely

Our abstention machinery is already the right substrate. Two additions, neither requiring a model:

1. **A distress route that is not an answer route.** If a query contains first-person harm language
   — "he touched me", "they fired me for complaining", "I am scared" — the correct output is not a
   better citation. It is: the SHe-Box portal, the district's Local Committee, the officer's name
   and address from the register we already hold, and a plain statement that this tool is not a
   person. We hold all 31 District Officers with names and emails. That is a genuine referral
   capability nobody else has wired up.

2. **Never price the distress path.** A complainant hitting a paywall while asking whether she can
   be sacked for complaining is the worst thing this product could do. Whatever the pricing model
   becomes, that route is free and stays free. Worth writing into the code as a rule, not a policy
   document.

This is also, incidentally, a moat. It is the part of the product a US legal-AI company will never
build for India, and unlike case-law coverage it costs nothing but care.

---

## 3. Honest scope note on the rest of the query set

The prompt asks for 15 searches, 3 sources each, then a prototype. I ran a focused subset and am
reporting what I actually did rather than implying coverage I do not have:

| Area | Status |
|---|---|
| Trauma-informed legal AI (Set B) | **researched**, above |
| Graph RAG / precedent relationships (B12) | **already done** — [Falkor-IRAC](https://arxiv.org/abs/2605.14665), and `provision_graph.py` + `trace()` implement it over statute |
| Hierarchical statute retrieval (B13) | **already done** — whole sections + 6 addressable sub-sections |
| Self-reflective RAG / critique (B15) | **measured and rejected** — `bench_safety.py`: self-similarity flagged two verbatim quotations as fabrications |
| Ratio decidendi, adversarial retrieval, multi-jurisdiction judgment prediction, FIR extraction, Indic Legal-BERT | **not researched** — all require a judgment corpus we do not hold |

That last row is the honest blocker for most of the ambitious query set. **Ratio decidendi
extraction, overruled-judgment tracking, adversarial counter-argument retrieval and analogical case
matching all operate on case law.** We have none. Researching techniques for a corpus we do not
possess produces a reading list, not a capability.

The prerequisite is not an algorithm. It is judgments — and the honest cheapest source is Indian
Kanoon's API, which is a corpus-ingestion task of the same shape as `ingest_posh.py`, with the same
byte-verification requirement.

---

## 4. Sequence

Ordered by what unblocks the most, with the constraint that nothing here beats the two human gates.

| | Work | Blocked on |
|---|---|---|
| 1 | **Distress route.** Detect first-person harm language; route to SHe-Box, the Local Committee, and the district officer we already hold. Free, always. | nothing |
| 2 | **Conflict panel in the existing frontend**, wording per §1.1 — quotes the provisions, states we hold no judgments. | nothing |
| 3 | **Gate 1.** Six clauses to a lawyer. Coverage 0% → 85%. | a lawyer |
| 4 | **Pricing**, after 3. | 3 |
| 5 | **Judgment corpus** via Indian Kanoon, byte-verified. Unblocks most of Query Set A. | ~₹500 of API credit |
| 6 | Ratio decidendi, adversarial retrieval, multi-jurisdiction comparison. | 5 |

Cause lists, vernacular and tribunals sit behind 5 for the same reason: they are all corpus
problems wearing algorithm costumes.

---

## 5. The one-line version

The strategy is right and the sequencing is inverted. **Build the distress route now because it
costs nothing and is the right thing to do; get the lawyer before the paywall because otherwise
you are charging for a refusal; and get judgments before researching judgment algorithms.**
