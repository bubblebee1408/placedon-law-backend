# Architecture deep dive: their design choices against our problem

## What this is, and the one thing it is not

This maps each capability Spellbook (and Harvey, and Legora) publicly claims to
the design pattern that capability *requires*, then asks the only question that
matters to us: **on Indian statutory compliance, does that pattern help a lawyer
or not** — and what position does our own code take on the same axis.

It is not a reconstruction of anyone's software. Their internals stay `OPEN`
unless a vendor page states them, for the reason recorded in
`SPELLBOOK_INFERRED_ARCHITECTURE.md`: a confident account of a competitor's code,
built from outside, is the fabrication `COMPETITOR_PATTERN_ANALYSIS.md` was
written to reject. Every claim about *us* below cites a file that exists.

The finding, stated first: **most of their architecture would actively harm a
lawyer on our problem, and the parts that would help are the cheap parts.** The
expensive parts of a contract-review system solve a problem statutory compliance
does not have, and the expensive parts of statutory compliance are ones a
contract product has no reason to build.

---

## The axis that separates the two problems

Everything below reduces to one difference, and it is worth stating plainly
because it is doing all the work:

> A contract is **private, singular, and static**. Statute is **public,
> versioned, and moving**.

A contract exists in one version — the one signed. Nobody amends it
retrospectively. It has no commencement date and no delegated instrument setting
its thresholds. The customer holds the truth, and the tool's job is to compare
that private truth against a market or a playbook.

A statutory obligation exists in as many versions as it has amendments. An
amending Act changes earlier text. A provision can be notified and not yet in
force. The operative figure often lives in a Rule the primary Act only gestures
at. The source is public — and, as `docs/SOURCE_DEFECTS.md` records across four
defects, sometimes wrong in the government's own rendering.

A design tuned for the first column is not neutral on the second. It is often
wrong on it.

---

## Capability by capability

### Similarity retrieval — "compare to thousands of similar agreements"

**Their pattern (LIKELY):** dense-vector retrieval. "Similar" is a
nearest-neighbour question, and neighbour search is what embeddings do well.

**Does it help a lawyer on our problem?** No — it actively hurts. The statutory
question is *"what did s.174 require on the meeting date"*, which is a **lookup**,
not a neighbour search. A vector index answers "here is a provision that reads
like your query", and a provision that reads *similar* to the right one is a
**wrong answer wearing the costume of a good one**. Worse, a lexical index goes
stale visibly — the amended text is simply not found — while a vector index keeps
returning a plausible stale neighbour with nothing in the path revealing it.
That is a self-inflicted version of the exact `STALE_TEXT` defect this product
exists to catch.

**Our position:** `checker/text_search.py` refuses embeddings, and the reason it
gives is not corpus size (464 sections is past the old threshold) but **query
shape and staleness invisibility**. Statutory queries name their subject —
"related party transactions", "quorum for board meetings" — so a drafter's own
vocabulary is a better key than a learned neighbourhood.

### Playbook comparison — "encode your legal standards"

**Their pattern (NECESSARY):** customer-authored rules per tenant, and a step
that evaluates a clause against them. **OPEN:** whether that step is a rule
engine or a model judging conformance.

**Does it help a lawyer on our problem?** The *mechanism* helps enormously — but
we do not have the input. There is no firm playbook in statutory compliance.
The comparison target is **the Act**, which is harder than a playbook in exactly
the way that matters: a playbook is static and a customer wrote it; the Act
moves and no customer controls it. So the pattern transfers, the data does not,
and the thing it compares against is the difficult part they never had to build.

**Our position:** `checker/obligations.py` is the register a playbook would be —
except its rows are generated from the law and the company's facts, not authored
by a customer. The obligation *is* the standard, and it is dated.

### Ask with citations — "answers you can trust, with citations"

**Their pattern (NECESSARY):** retrieval before generation, document identity
carried to the output. **OPEN (twice):** whether a citation resolves to a
passage or a document, and whether the cited text is *checked against* the
answer or merely retrieved alongside it.

**Does it help a lawyer?** Only as much as those two OPENs resolve. A citation to
a 50-page document a lawyer must then search is a worse product than one that
lands on the sentence — and "retrieved alongside" is not "supports the claim".
These are the two questions a buyer cannot answer from any of their four public
pages, and they are the two that decide whether the citation is trustworthy or
merely present.

**Our position:** `checker/evidence_pack.py` is the closed world — *the only
thing a model is ever shown* — and `checker/model_adapter.py` rejects a citation
to any id not in the pack, "not repaired". A span carries its sha256, verified
against the frozen hash by `benchmark_v2_freeze.frozen_rows`. So for us both
OPENs are closed by construction: a citation is a span, and it is checked. That
is the one place our architecture is unambiguously ahead, and it is ahead
*because* our ground truth is fixed public text a hash can pin.

### Multi-document agents — "Associate", "end-to-end"

**Their pattern (NECESSARY):** orchestration with state outliving a single call.
**OPEN:** fixed graph or model-chosen plan.

**Does it help a lawyer on our problem?** The orchestration helps; the
*model-chosen plan* is where we diverge hard. `docs/AGENT_ARCHITECTURE_PLAN.md`
argues the planner must be deterministic, because a model choosing the next step
is a model choosing which law applies — the one decision `applicability.py`
exists to keep away from a model. On contracts that risk is smaller; the law
that applies is rarely the question. On statutory compliance it is the whole
question.

### Redline in Word

**Their pattern (LIKELY):** the hard part is a tracked change that survives
Word's revision model, on documents in every state Word permits.

**Does it help a lawyer?** Yes, genuinely, and it is the capability we most
plainly lack — but it is **drafting**, not verification, and it is ordinary
software. It helps a lawyer *produce* a document. It says nothing about whether
the document is *correct*, which is our entire wedge.

---

## Where a lawyer is actually helped, and where the design only looks like help

**Genuinely helped by their design:** producing and revising documents (redline,
draft), and surfacing unusual clauses against a market they can see. These are
real and we do not do them.

**Only apparently helped:** an "answer with a citation" whose citation is a
document rather than a passage, or is retrieved rather than checked, *looks* like
grounding and is not. A 60%-of-contracts-have-errors statistic (their
`Humans Hallucinate Too` report) *looks* like an accuracy claim and is a claim
about the corpus measured by the tool itself, with no false-positive rate — see
`SPELLBOOK_INFERRED_ARCHITECTURE.md` §4a. A lawyer is helped by the first appearance
and misled by the second, and telling them apart requires exactly the two OPEN
questions above.

**Not helped at all, on our problem:** similarity retrieval, because the
statutory question is a dated lookup and a similar answer is a wrong one.

---

## What this says our architecture should do

1. **Keep retrieval lexical and dated.** Confirmed against a competitor's likely
   design, not just in the abstract: `text_search.py` holds, and the reason is
   staleness invisibility, not corpus size.
2. **Keep the planner and applicability deterministic.** Their agent language
   trends toward model-chosen plans; on statute that is the one place a model
   must not decide.
3. **Press the one real advantage.** Span-level, hash-checked citation over fixed
   public text is a thing a contract product cannot cheaply replicate, because
   its ground truth is private and mutable and ours is public and pinnable.
4. **Build the cheap things they have and we lack** — a working surface, and
   eventually drafting — but *after* the wedge, and knowing they are table
   stakes rather than the moat.
5. **Publish the number nobody else publishes.** The deepest finding of this
   whole competitor pass is that the bar for a defensible accuracy claim in legal
   AI is low. A false-positive rate against practitioner-labelled ground truth
   would say something none of the three comparators says. We cannot today — 67
   constructed pairs, one non-lawyer reviewer — but it is reachable, and it is
   worth more than any feature on this page.

---

## What stays unknown, and how to close it

Four things decide whether points 1–3 are real advantages or merely differences,
and none can be settled from outside:

- whether their citations are passages or documents (Ask),
- whether cited text is checked or merely retrieved (Ask),
- whether Playbook conformance is a rule engine or a model (Playbooks),
- whether they apply past-dated law to a past contract (the whole of §3 in
  `SPELLBOOK_INFERRED_ARCHITECTURE.md`).

`docs/VENDOR_QUESTIONS.md` asks all four, openly, as an evaluating buyer. That is
the only honest way to close them, and it is a better way than any account
access would be, because a vendor's own answer is citable and an inferred one is
not.
