# Spellbook — everything in one place

A single dossier on Spellbook, drawn together from the fuller documents
(`COMPETITOR_FEATURE_MATRIX.md`, `SPELLBOOK_INFERRED_ARCHITECTURE.md`,
`ARCHITECTURE_DEEP_DIVE.md`, `VENDOR_QUESTIONS.md`). Read this for the whole
picture; read those for the reasoning behind each part.

**Sourcing, stated once and true throughout:** every fact here comes from
Spellbook's own public pages, read 2026-09-01 and 2026-09-03 — homepage,
security page, Associate page, pricing page, blog. No account was used, no
authenticated area accessed, no internals observed. `spellbook.legal` redirects
to `spellbook.com`; `docs.spellbook.legal`, `/product/associate` and `/ask` do
not resolve. Where a design is undetermined from outside, this says `OPEN`
rather than guessing.

---

## 1. What they sell

| Surface | Their words |
|---|---|
| Spellbook Associate | "The AI agent for multi-document drafting and review" |
| ACM (Autonomous Contract Management) | "The first AI system that powers contracts end-to-end" |
| Review | "Spot risks and add redlines to your contracts—right in Word" |
| Draft | "Draft clauses and documents from scratch, or use your preferred precedents" |
| Compare | "Compare your contracts to thousands of similar agreements" |
| Ask | "Quick answers to complex questions"; "Answers you can trust, with citations" |
| Playbooks | "Encode your legal standards" |

Word and Google Docs without switching windows; intake from email, Slack,
Salesforce. Zero data retention negotiated with OpenAI and Anthropic; processing
in Canada and the US; SOC 2 Type II, HIPAA, GDPR.

They serve **commercial contracts**. That single fact explains everything below.

---

## 2. Business model

**Pricing is not published.** Per-seat, sales-led, behind a 7-day trial;
dedicated support starts at ten seats; the in-house tier includes a "Playbook
Build Service".

The structural reading:

- **The playbook is the lock-in, not the model.** Anyone can rent the same LLM.
  Nobody else has your encoded standards, and a customer who has *paid* to encode
  them has a switching cost the software alone never creates. Same idea as
  Legora's "Lists" and Harvey's "Memory" — a moat available with no proprietary
  model at all.
- **The trial feeds a sales close.** Product-led entry, sales-led price. They
  want you inside before the price conversation.
- **Per-seat pricing set by negotiation, on a product built for North American
  firms, is unlikely to reach a four-person practice in Pune.** Not a product
  flaw — the go-to-market is not aimed there, and that is more durable than a
  feature gap.

---

## 3. What each feature requires underneath

Marked `NECESSARY` (the feature cannot work without it), `LIKELY` (a competent
team almost certainly does it), or `OPEN` (undetermined from outside).

- **Compare to similar agreements** — NECESSARY: a corpus of agreements they hold
  independent of the customer, and retrieval over it. LIKELY: dense-vector
  (similarity) retrieval. OPEN: where the corpus comes from.
- **Playbooks** — NECESSARY: customer rules per tenant and a comparison step.
  OPEN, and the most interesting unknown: whether that step is a rule engine or a
  model judging conformance.
- **Ask with citations** — NECESSARY: retrieval before generation. OPEN twice:
  whether a citation resolves to a passage or a document, and whether the cited
  text is *checked against* the answer or merely retrieved alongside it.
- **Review / redline in Word** — LIKELY: the hard part is a tracked change that
  survives Word's revision model, not the model call.
- **Associate / ACM** — NECESSARY: orchestration with state across calls. OPEN:
  fixed graph or model-chosen plan.

---

## 4. Their one public accuracy claim, and what it is worth

*"Spellbook Labs Report: Humans Hallucinate Too."* Their most informative page.

Measured: 3,019 EDGAR contract exhibits, 2005–2026, 500+ companies, analysed with
Spellbook Review. Reported **60% of contracts had drafting errors**; 2.5%
high-risk; 1.15 issues per contract. To their credit it states its own limits:
*"a proxy"*, *"deliberately conservative"*, *"the floor, not a full account"*.

**What it does not establish, and this is the point.** It measures how many
contracts contain errors *using Spellbook Review as the instrument*. It never
measures how often that instrument is **right**. No count of validating human
reviewers, and no false-positive rate anywhere. If the tool flags 60% of
contracts, how many of those flags are wrong is the question a buyer needs, and
the report does not ask it.

That is a claim about the corpus, not the tool, and it is self-graded. Recorded
not as a jab but as calibration: **the bar for a defensible accuracy claim in
legal AI is currently low.**

---

## 5. What this means for Placedon

The whole comparison turns on one difference:

> A contract is **private, singular, static**. Statute is **public, versioned,
> moving**.

From that, three consequences:

**Most of their architecture would hurt a lawyer on our problem.** Similarity
retrieval answers "here is a provision that reads like your query", and on
statute a provision that reads *similar* to the right one is a **wrong answer** —
and a stale one the retrieval path hides, which is a self-inflicted version of the
exact defect this product exists to catch.

**The parts that transfer, transfer without their data.** The playbook pattern is
strong, but there is no firm playbook in statutory compliance; the comparison
target is the Act, which moves and no customer controls — the hard part they never
had to build.

**The one place we are unambiguously ahead is span-level, hash-checked citation
over fixed public text** — and we are ahead *because* our ground truth is public
and pinnable while theirs is private and mutable. For us both of Ask's OPEN
questions are closed by construction.

**The one place they are plainly ahead is drafting** — redline in Word. Real,
we lack it, and it is table stakes rather than a moat: it helps a lawyer
*produce* a document, not know whether it is *correct*.

**And the opening the accuracy report reveals:** a false-positive rate against
practitioner-labelled ground truth would say something none of the three
comparators says. We cannot today — 67 constructed pairs, one non-lawyer reviewer
— but it is reachable, and worth more than any feature.

---

## 6. What only they can answer

Four questions decide whether §5 is real advantage or mere difference, and none
is answerable from outside:

1. Do Ask's citations resolve to a passage or to a document?
2. Is the cited text checked against the answer, or merely retrieved?
3. Is Playbook conformance a rule engine or a model?
4. For a contract signed in 2019, does it apply the law as it stood in 2019?

`VENDOR_QUESTIONS.md` asks all four, and fourteen more, openly, as an evaluating
buyer. A vendor's own answer is citable; an inferred one is not. That — not an
account login — is the honest way to close what is still open.
