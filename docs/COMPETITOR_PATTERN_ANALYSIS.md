# Competitor pattern analysis — Legora and Harvey

Written 2026-08-31. **Nothing in this document verifies a competitor fact.** It classifies claims
from an unattributed document and extracts the engineering patterns that survive classification.

## How to read this

The input was a document of unknown authorship, plausibly model-generated, handed to us without a
single source anchor — no URL, no press-release date, no paper title, no named spokesperson, no
filing reference. Web access was unavailable for this pass, so **no claim below was checked against
any source.**

Three rules govern the writing, and they are the repo's own:

1. `CLAUDE.md`: *"No unsupported product, market, legal, or competitor claims."* and *"If evidence
   is incomplete, write OPEN or UNVERIFIED. Do not guess."*
2. `docs/TECHNICAL_PLAN.md` §2 already retired one competitor claim of exactly this shape —
   *"Harvey uses OpenAI GPT-4 + proprietary RAG + human-in-the-loop"* → **"Unverified. Do not repeat
   it to an investor."** This document must not reintroduce it by restating it more fluently.
3. `checker/model_adapter.py`, prompt rule 1: *"Your own knowledge ... is NOT evidence here and must
   not appear in your answer."* That rule binds the author of this document too. Where the analysis
   below draws on a language model's recollection of industry facts, it is marked as recollection
   and classed no higher than PLAUSIBLE. **Model memory is not a citation.** This is the same
   discipline `checker/evidence_pack.py` enforces on the closed world: a fact not in the pack is
   unassertable.

Classification vocabulary, aligned to `docs/EVIDENCE_PROTOCOL.md`:

| Class | Meaning | Downstream permission |
|---|---|---|
| **PUBLISHED GENERAL TECHNIQUE** | The *technique* is public engineering literature, independent of any company. Its **attribution** to a named company is a separate, unverified claim. | Safe to reason from as a technique. Never safe to attribute. |
| **PLAUSIBLE BUT UNVERIFIED** | Consistent with how such products are built or with general recollection; no source held. | Internal reasoning only. Never in a deck, product page, or investor conversation. |
| **SUSPICIOUS — LIKELY FABRICATED** | Carries positive markers of reverse-engineering or hallucination. | Treat as false until a primary source says otherwise. Do not repeat even hedged. |

A fourth state is used where needed: **UNFALSIFIABLE FROM OUTSIDE** — a claim about a private
company's internal architecture that no amount of public research can confirm or deny. These are the
most dangerous claims in the input document, because they are unverifiable *and* undisprovable, so
they survive scepticism by default.

---

## 1. Claim-by-claim classification

### 1.1 Legora (formerly Leya)

| # | Claim | Class | Reasoning |
|---|---|---|---|
| L1 | Did not train a foundation model; integrates third-party models (Claude, GPT) | **PLAUSIBLE BUT UNVERIFIED** | Structurally the default for an application-layer legal vendor, and it is the same conclusion `docs/MODEL_PLAN.md` reached independently on our own constraints. Believable is not verified. Note the asymmetry: a *negative* capability claim ("did not train") is close to unfalsifiable from outside — absence of a published model is not proof of absence of a model. |
| L2 | Serves models via Azure | **PLAUSIBLE BUT UNVERIFIED** | Cloud-vendor routing is ordinary and often stated on a vendor trust page. Trivially checkable when web returns; not checkable now. Low stakes either way — it changes nothing we build. |
| L3 | Proprietary "agent frameworks" | **UNFALSIFIABLE FROM OUTSIDE** | "Proprietary framework" is a content-free description. It asserts that something exists and is theirs, which cannot be disproven and confers no transferable information. Marketing vocabulary, not architecture. |
| L4 | Features named "tabular review" and "Workflows" | **PLAUSIBLE BUT UNVERIFIED** | Feature *names* are the most checkable class of claim here — they either appear on a product page or they do not. Both names are also generic enough to be guessed from the category. Verify by name, not by inference. |
| L5 | RAG: chunking, embeddings, vector DB | **PUBLISHED GENERAL TECHNIQUE** (attribution unverified) | Retrieval-augmented generation is Lewis et al., NeurIPS 2020. Dense passage retrieval is Karpukhin et al., EMNLP 2020. The technique is public and we may reason from it freely. That *this vendor* uses it is an unsourced guess — and it is the single most guessable architectural claim anyone can make about a 2026 legal-AI product, which is precisely why its presence in the document carries near-zero information. |
| L6 | Hybrid dense + sparse (BM25) retrieval with a reranker | **PUBLISHED GENERAL TECHNIQUE** (attribution unverified) | BM25 is Robertson & Walker 1994; the idf half is Spärck Jones 1972 — both already cited in `checker/retrieval.py`. Hybrid sparse+dense fusion and cross-encoder reranking are standard IR practice (e.g. Nogueira & Cho 2019 on BERT rerankers; reciprocal-rank fusion for combining runs). Reason from the technique. Do not attribute. |
| L7 | Multi-agent loop: Orchestrator → Extraction → Analysis → **Critic**, with self-correction | **SUSPICIOUS — LIKELY FABRICATED** *(as a description of their internals)*; the underlying pattern is **PUBLISHED GENERAL TECHNIQUE** | Two things are tangled. (a) Self-critique / self-refinement loops are published — Self-Refine (Madaan et al. 2023), Reflexion (Shinn et al. 2023), CRITIC (Gou et al. 2023), and Self-RAG (Asai et al. 2023), which `docs/TECHNICAL_PLAN.md` already flagged for overstated gains. (b) The specific four-stage pipeline with those four node names is **exactly what an outside observer would guess**, and that is the tell. It is the canonical textbook decomposition, not a leaked design. Any real system's stage list is idiosyncratic — it carries the scars of its failures (ours does: E3/E4/E5/E6 are named after the *error shapes* they were built to catch, and no one could guess them from outside). A stage list with no scars was not observed; it was inferred. |
| L8 | Sentence-level citations hyperlinked to source coordinates | **PUBLISHED GENERAL TECHNIQUE** (attribution unverified) | Span-grounded attribution is a public research area — attributed QA / AIS (Rashkin et al. 2021), ALCE (Gao et al. 2023). Offset-anchored citation is ordinary engineering. Whether this vendor does it sentence-level or paragraph-level is exactly the sort of detail a guesser upgrades and a user could disprove in one screenshot. |
| L9 | Word / Outlook add-ins | **PLAUSIBLE BUT UNVERIFIED** | Directly checkable on a Microsoft AppSource listing when web returns. Low-risk claim; also see §4 — the pattern's *relevance* to us is the real question, not its truth. |
| L10 | Integrations with Box / iManage / NetDocuments | **PLAUSIBLE BUT UNVERIFIED** | These are the three named DMS vendors anyone would list for the Anglo-American legal market; producing the list requires no knowledge of the product. Verifiable from an integrations page. |
| L11 | Zero-data-retention enterprise terms | **PLAUSIBLE BUT UNVERIFIED** | A contractual term, not an architecture. Verifiable only from the actual contract or a trust-page statement; a marketing summary of a contract is not the contract. |
| L12 | SOC 2 Type II and ISO 27001 | **PLAUSIBLE BUT UNVERIFIED** — *and uniquely settleable* | Unlike everything else in this table, certification produces an external artefact: a named auditor, a report date, a certificate number, an accredited certification body. Either those exist or the claim is false. This is the one claim where "unverified" is a temporary state rather than a permanent one. |
| L13 | Built alongside lawyers at a named law firm | **PLAUSIBLE BUT UNVERIFIED** | Design-partner claims are usually press-released by both sides, so a two-sided source is achievable. Until then it is a marketing origin story. Note its function in the document: it lends *human* credibility to the surrounding *technical* claims, which is a rhetorical structure, not evidence. |
| L14 | Published a "Benchmark for Agentic Reasoning (BAR)" | **PLAUSIBLE BUT UNVERIFIED**; *its results are ANECDOTE-class regardless* | A vendor-authored benchmark on which the vendor scores well is not evidence about the vendor, per `docs/EVIDENCE_PROTOCOL.md`. Even fully verified, it would enter our ledger as vendor self-report. `checker/metric_policy.py` states the reason precisely: a score without its majority-class baseline is not a result, and Afane et al. (CSLAW 2026) measured an all-affirmative baseline at F1 0.73 beating two commercial legal-AI products. Any benchmark that does not publish its baseline and its abstention rate is uninterpretable. |
| L15 | Published an ROI report | **PLAUSIBLE BUT UNVERIFIED**; *ANECDOTE-class regardless* | A vendor ROI report is a sales artefact. Same treatment as L14. |
| L16 | Partnership with a named third party | **PLAUSIBLE BUT UNVERIFIED** | Two-sided press-release check. Nothing turns on it for us. |

### 1.2 Harvey

| # | Claim | Class | Reasoning |
|---|---|---|---|
| H1 | Founded 2022 by a litigator and an ex-DeepMind/Meta researcher | **PLAUSIBLE BUT UNVERIFIED** | This matches general recollection, and per the header rule that recollection is **not evidence**. It is also the most widely-reported fact about the company, hence the easiest for a generator to reproduce correctly — so its correctness lends *no* credibility to the technical claims stacked behind it. That stacking is the document's core rhetorical move: verifiable trivia in front, unfalsifiable internals behind. |
| H2 | Early exclusive GPT-4 access via the OpenAI Startup Fund | **PLAUSIBLE BUT UNVERIFIED**; "exclusive" is the suspicious word | Investment by a named fund is checkable from a portfolio page. **"Exclusive"** is a strong, quantified-sounding qualifier that is almost never what such arrangements actually are, and it is the kind of word a generator adds for narrative force. Treat the investment as plausible and the exclusivity as unsupported. |
| H3 | "Vault" handling up to **100,000** documents with parallel agents | **SUSPICIOUS — LIKELY FABRICATED** *(as stated)* | Three markers. (a) The number is round, memorable and quotable — the shape of a marketing ceiling, not an engineering limit; real limits are odd (`corpus/companies_act` holds 527, our index maps 474/517). (b) A capability ceiling is meaningless without the accompanying constraint — per-matter or per-tenant? concurrent or cumulative? what latency, what cost, what accuracy at that size? A sourced claim carries at least one of those; a generated one never does. (c) "Parallel agents" is the architecture anyone would guess for a large-N document task. The product name may well be real; the number and the mechanism are decoration. |
| H4 | Three-layer stack: foundation / orchestrator / tool bundles | **UNFALSIFIABLE FROM OUTSIDE**, with fabrication markers | This is the generic agent-architecture diagram from any 2024-2026 conference talk, relabelled. Same defect as L7: it is what you would draw if you had never seen the system. "Tool bundles" in particular is vocabulary in search of a referent. |
| H5 | Eval gates against partner-authored "Golden Datasets" | **PUBLISHED GENERAL TECHNIQUE** (attribution unverified) | Held-out expert-labelled eval sets gating release is standard ML practice and predates all of these companies. The idea is safe to adopt (and we have a stricter version — see §2, P5). The specific term and its attribution are unsourced. |
| H6 | Citation anchoring | **PUBLISHED GENERAL TECHNIQUE** (attribution unverified) | Same as L8. |
| H7 | **August 2026: released a proprietary model "Tenet", built by post-training "Kimi K3" from Moonshot AI using "Asynchronous Reinforcement Learning"** | **SUSPICIOUS — LIKELY FABRICATED** | Detailed below. This is the load-bearing suspicious claim and it fails on seven independent markers. |

---

### 1.3 Why H7 (Tenet / Kimi K3) reads as fabricated

This claim deserves separate treatment because it is the one a reader would most want to act on, and
because it demonstrates the general markers cleanly. **We could not check it.** The finding is not
"this is false"; it is "this exhibits the signature of a constructed claim, so the prior against it
is high and it must not be repeated in any form."

**Marker 1 — version-number extrapolation.** To the limit of this model's recollection, Moonshot
AI's publicly released line ran k1.5 and K2. "K3" is the *next integer*. Incrementing the last known
version of a real product is the single most common way a fabricated claim about a fast-moving field
gets generated: the name is right-shaped, right-branded, and requires no knowledge. Compare the
failure class already recorded in this repo — `docs/PROVIDER_DECISION.md` and
`docs/TECHNICAL_PLAN.md` caught three separate documents naming `claude-3-5-sonnet-20241022`
(retired), `@anthropics/claude-code` (404, wrong scope) and a shut-down Gemini 1.5. Identifiers rot
and identifiers get invented; both produce a plausible string that fails on first contact with
reality. K3 may well exist by now. That is not the point — the point is that the claim gives us no
way to tell, and neither did its author.

**Marker 2 — a real technique name doing credibility work.** "Asynchronous Reinforcement Learning"
is a genuine and long-standing family — asynchronous actor-learner methods go back to A3C (Mnih et
al., ICML 2016), and decoupling rollout generation from policy updates is a live theme in modern
RLHF/RLVR training infrastructure. Because the term is real, it survives a shallow sniff test. This
is the characteristic construction of a hallucinated technical claim: **a real technique + a real
company + an invented specific**, assembled so the checkable parts vouch for the unchecked one. Note
that the phrase is also used at exactly zero resolution — no objective, no reward signal, no data
source, no reason why *async* RL specifically is the right tool for legal post-training. A claim
sourced from an engineering blog carries at least one of those.

**Marker 3 — dated to the immediate present.** The document places the release in the current month.
Present-dated claims are maximally unverifiable (nothing has been written about them yet, no
secondary coverage exists, no archived page) and maximally persuasive (they explain why you had not
heard of it). This is the temporal equivalent of the placeholder citation described in
`docs/LEGAL_AI_ARCHITECTURE_ANALYSIS.md` §1.1: *"a placeholder that looks like a citation is a
fabrication with a UI around it."* A date that looks like news is a fabrication with a timeline
around it.

**Marker 4 — a proper noun with no artefacts.** A named proprietary model normally arrives with a
model card, a benchmark table, a system card, a pricing line, or at minimum a blog post. The claim
supplies a name and nothing else. Equally, the K1.5/K2 releases were, to recollection, accompanied
by public weights and technical reports; **the absence of a public repository or technical report for
a "K3" would be close to decisive against this claim**, and that is a cheap check (see §5).

**Marker 5 — unaddressed structural tension.** A vendor whose entire value proposition to
Anglo-American law firms is enterprise trust, data residency and procurement acceptability
(cf. L11/L12 in the same document) building its flagship on a Chinese-lab open-weights base is not
impossible — open weights can be self-hosted, which is arguably *better* for residency — but it is a
decision with obvious procurement consequences that any real announcement would have addressed
head-on. The claim addresses nothing. Fabricated claims are internally frictionless because the
generator never had to survive a customer question.

**Marker 6 — no licence reasoning.** Post-training someone else's base model is first a *licence*
question and only second an engineering one. Our own `docs/MODEL_PLAN.md` records the licence of
every candidate (InLegalBERT MIT; ILDC/HLDC/IL-TUR non-commercial and therefore refused). A real
account of building a proprietary model on a third-party base would name the licence, because that
is the first thing anyone in the room asks. Silence on it is the silence of someone who never had
the meeting.

**Marker 7 — it is the claim the document most wants you to believe.** It converts an
application-layer company into a model company, which is the highest-status possible framing and the
one most likely to change a reader's strategy. Claims that are simultaneously the most consequential
and the least sourced in a document are where fabrication concentrates.

**Consequences for this repo.** H7 must not appear in any deck, plan, or investor conversation, even
hedged as "reportedly". If it were true it would change nothing we build: `docs/MODEL_PLAN.md` refuses
foundation-model work on data-rights and budget grounds, and the moat is stated as statutory currency
and the admission gate — *"A better model does not close that gap and a worse one does not open it."*
A competitor's model is a fact about them, not a threat to that thesis.

### 1.4 The generic markers, extracted

Useful beyond this document. A competitor-architecture claim is probably reverse-engineered rather
than sourced when it shows:

1. **Guessable stage names.** The pipeline is the canonical textbook decomposition. Real pipelines
   are named after the failures that produced them.
2. **No scars.** No abandoned approach, no measured regression, no "we tried X and it was worse". All
   real engineering writing contains these; invented writing never does, because failure is the part
   you cannot guess.
3. **Round numbers.** 100,000 documents. Marketing ceilings are round; engineering limits are not.
4. **Real term + invented specific.** A genuine technique name carrying an unsourced proper noun.
5. **Version-integer extrapolation.** The next number after the last real release.
6. **Present-dating.** The event is too recent to have secondary coverage.
7. **Checkable trivia in front of unfalsifiable internals.** Founder names and dates (verifiable,
   and correct) positioned to lend authority to architecture claims (unverifiable).
8. **Zero source anchors anywhere in the document.** Not one URL, DOI, filing, or dated page — while
   the content is entirely composed of the kind of facts that have sources.
9. **Frictionlessness.** No licence question, no procurement objection, no cost, no trade-off. Real
   decisions cost something and the account says what.

---

## 2. Transferable engineering patterns

Stated generically, with **no company attribution**. Each is either a published technique or an
obvious consequence of the problem, and each is assessed against what this repo already holds.

| # | Pattern (generic) | Placedon status | Evidence in repo |
|---|---|---|---|
| P1 | **The model is the least-trusted component.** It receives a closed world, may not use its own weights as evidence, and its output is parsed into a rigid structure that fails closed. | **HAVE — stronger than the input document describes for anyone** | `checker/model_adapter.py` (three pre-call refusals; malformed output → `INSUFFICIENT_EVIDENCE`, never an exception), `checker/evidence_pack.py` (closed world stated as prohibition, not preference) |
| P2 | **Separate the model boundary from the corpus.** Whatever crosses the boundary *is* the universe; anything withheld must be visibly marked withheld, never silently dropped. | **HAVE** | `checker/evidence_pack.py` — "a provision that silently disappears looks to the model exactly like a provision that does not exist" |
| P3 | **Admission control: existence ≠ admissibility.** Material may be acquired, hashed, parsed and searchable and still be barred from a model-facing pack. Asymmetric review/model modes. | **HAVE — and this is differentiating.** Nothing in the input document describes an equivalent for either product. | `checker/admission.py` (`MODE_REVIEW` vs `MODE_MODEL`, blocked-not-dropped reporting) |
| P4 | **Verification is a separate stage from generation, with a verdict vocabulary that cannot overclaim.** A citation proves the authority exists; it does not prove the proposition follows. | **HAVE — unusually rigorous** | `checker/grounding_policy.py` (seven-state path; only the last two may yield GROUNDED), `checker/claim_verifier.py` (`SUPPORTED` deliberately unreachable; tops out at `LEXICAL_CANDIDATE`) |
| P5 | **A deterministic specialist cascade with explicit roles**, each member built against a named error shape, one member permitted only to refuse. | **HAVE — and it is the honest replacement for a "Critic agent"** | `checker/metric_policy.py` `MODULE_ROLES` (E3 GENERAL, E4/E5 SPECIALIST, E6 GATE); `entail_baseline` (E3, token presence), `entail_binding` (E4, quantity→obligation binding), `entail_role` (E5, unit class / complement / relation), `entail_qualifier` (E6, dropped provisos) |
| P6 | **Release gates on a frozen eval set** — but gated on four conditions, not accuracy: absolute false-accept ceiling, F1 floor, abstention cap, per-bucket reporting, majority baseline printed always. | **HAVE — a strictly stronger formulation than a pass/fail "golden dataset"** | `checker/metric_policy.py` (ceiling 10, F1 floor 0.40, abstention cap 0.25), `checker/benchmark_v2_freeze.py` (raises rather than silently dropping bad records) |
| P7 | **Labels correct-by-construction; the model may propose but never sign off.** Split fixtures by *how the label was established* (constructed / source-checked / human-judged) and exclude unapproved human-judged from any frozen set. | **HAVE** | `checker/entail_mine.py`, `checker/entail_pairs_v2.py`, `checker/grounding_policy.py` constants, `checker/review_table.py` ("Decides nothing") |
| P8 | **Abstention measured as recall over items that are unanswerable by construction**, not as a rate. | **HAVE** | `checker/eval_taxonomy.py` — withhold the provision a claim depends on; refusal is the only correct behaviour |
| P9 | **Hybrid retrieval where the *exact* route is first-class**: citation syntax resolves structurally and returns nothing when unmapped; free text falls back to corpus-measured idf weighting. | **HAVE (sparse + structural half)** | `checker/legal_retrieval.py` (exact, "a number is not an identity", defects travel with the text), `checker/text_search.py` (idf over 464 records, heading gain, no length prior), `checker/retrieval.py` (keyword route + scan floor) |
| P10 | **Reranking as a distinct stage** after first-pass retrieval. | **PARTIAL / OPEN** | `text_search.py` hand-built heading-gain scoring is a rerank in effect; `docs/MODEL_PLAN.md` names InLegalBERT (MIT) for the job, unbuilt. The published technique is safe; the open question is whether a rerank can carry a citable reason (§3). |
| P11 | **Span-level citation anchored to source coordinates**, resolved from an instrument rather than guessed. | **PARTIAL** | `checker/witness_span.py` resolves span boundaries from the amending Act rather than guessing; `checker/span_inventory.py`. But served answers cite at section level, not character offsets into the served text. **This is the clearest borrowable gap** — and it is a published technique (attributed-QA / span attribution), not a competitor secret. |
| P12 | **A grid review surface: rows = documents, columns = questions**, each cell traceable to its evidence. | **PARTIAL — and cheap** | `checker/review_table.py` already assembles a per-item grid (premise, qualifier inventory, preserved/missing/N-A) for fixtures. The pattern is the same; the axes differ (see §4.4). No new dependency required. |
| P13 | **Named, versioned, replayable pipelines** rather than free chat turns, so a run can be re-executed and diffed. | **PARTIAL** | `checker/s173_slice.py`, `checker/s96_slice.py`, `PROMPT_VERSION = "closed-world-v1"` in `model_adapter.py`, `benchmark_freeze` / `benchmark_v2_freeze`. No user-facing workflow object. |
| P14 | **Human-in-the-loop as explicit machinery**: a queue, immutable records, approval states, promotion previews, resubmission, scoped retraction. | **HAVE — strongly** | `checker/review_queue.py`, `review_record.py`, `promotion_preview.py`, `resubmission.py`, `scoped_retraction.py`, `admission.py` (immutable records + audit events) |
| P15 | **Meet the user in the surface where the work happens** rather than making them visit a web app. | **NOT HAVE — and the specific surface does not transfer** (§4.1) | — |
| P16 | **Publish an evaluation with its baseline** so a buyer can interpret it. | **HAVE as policy, NOT as an external artefact** | `metric_policy.py` requires the majority baseline with every result. `docs/CLAIMS_LEDGER.md` records zero lawyer review, so no external accuracy claim is permitted yet (`EVIDENCE_PROTOCOL` Tier 5). |

**The summary judgement on §2:** of sixteen extractable patterns, this repo already holds eleven
outright and three partially. The two genuine gaps (P11 span offsets, P15 surface) are both
published, ordinary engineering — not moats. **Nothing in the input document describes a capability
this project lacks the ability to build.** What it describes is a company that has customers.

---

## 3. Anti-patterns at this scale and budget

### 3.1 Vector database + embedding stack for the statutory corpus — ANTI-PATTERN, but the *stated* reason needs correcting

The brief said `checker/retrieval.py` "already argues against vector search for a ~500-section
corpus." **It does not, and the distinction matters.** `retrieval.py` argues against it for **30
sections** (the PoSH corpus) and explicitly concedes the opposite at 500:

> *"When the corpus reaches the four labour codes (~500 sections) this becomes the right call; today
> it is cargo cult."*

The Companies Act corpus is **527 ingested sections, 474 mapped**. By `retrieval.py`'s own stated
threshold, its argument has **expired**. Anyone citing `retrieval.py` to refuse embeddings on the
Companies Act is citing a document that says the reverse. This should be corrected wherever it is
repeated — including in `docs/TECHNICAL_PLAN.md` §2, whose table cites the 30-section arithmetic
against a blueprint that was indexing the Act.

The refusal is still correct, but it stands on `checker/text_search.py`'s reasoning, which is a
different and better argument:

> *"At 464 that argument no longer settles it by size alone — but query shape still settles it."*

Three grounds survive scrutiny:

1. **Query shape.** Users arrive with the drafter's own vocabulary — "related party transactions",
   "quorum for board meetings", "loans to directors" — because the drafter chose headings from the
   reader's vocabulary. Lexical matching against a heading is not an approximation of the right
   answer; it *is* the right answer. `docs/NON_GOALS.md` already cites Sciavolino et al. (EMNLP 2021)
   for BM25 winning on entity-rich exact match.
2. **Citability.** A lexical hit yields a reason a lawyer can audit — *"your words are in the
   heading"*. A cosine distance yields a number. In a product whose entire claim is evidence, an
   unauditable ranking is a liability, and `claim_verifier.py` documents where an unauditable score
   with a confident label leads.
3. **Staleness invisibility — the strongest ground, and it is about the moat.** The corpus is
   hash-stamped and the amendment ledger holds 451 records. When a section is amended, a lexical
   index over the current text is correct the moment the text is replaced. A vector index is not:
   the old vectors keep returning plausible neighbours and **nothing in the retrieval path reveals
   that they are stale.** Silent staleness is exactly the failure this product exists to detect
   (`docs/CLAUDE.md`: STALE_TEXT — "serving repealed law as current"). Introducing a component whose
   staleness is structurally invisible, into a product whose moat is statutory currency, is a
   self-inflicted version of the defect we sell against.

**The arithmetic, stated honestly, because two of the usual numbers do not survive:**

- *Dependency weight:* ~2 GB (torch + sentence-transformers) plus seconds of cold start, against a
  scan measured at 0.05 ms over the PoSH corpus. Still a real cost, and `CLAUDE.md` requires a stated
  reason for any new dependency. **Holds.**
- *Embedding money cost:* 527 sections × roughly 2,000 tokens ≈ **1.05 M tokens** to index. At
  commodity embedding rates this is **cents, one time**, and re-embedding on amendment is a few
  sections at a time. **This argument does not hold and should stop being made.** Cost is not why we
  refuse.
- *Recurring engineering cost:* every amendment requires re-embed + index rebuild + a way to prove
  the rebuild happened, i.e. a second currency-tracking system parallel to the one that is already
  the product. **Holds, and this is the real number** — it is measured in maintained code paths, not
  rupees.

**Verdict: refuse, on query shape, citability and staleness-invisibility — not on size and not on
cost.** The condition that would reverse it is stated in `text_search.py`: the query class whose
vocabulary appears nowhere in the statute ("whistleblower" for s.177's "vigil mechanism", "conflict
of interest" for s.184's "concern or interest"). The prescribed fix there is a **curated synonym
layer evidenced section by section**, which preserves citability. If that layer proves unmaintainable
at scale, embeddings become the argument again — as a *candidate generator* whose hits must still be
justified lexically before serving, never as the ranking of record.

### 3.2 A "Critic" LLM in the loop — ANTI-PATTERN, on evidence rather than budget

A self-correcting critic stage is a published technique (§1.1 L7), and it is still wrong here.
`docs/MODEL_PLAN.md` records the reason and it is not cost:

> *"LLM-as-judge is unsafe here. Magesh et al. refused it outright; Cymbler et al. used deterministic
> regex nuggets because an LLM judge inherits the same recency bias it is meant to detect."*

A critic drawn from the same model class inherits the generator's failure modes — including the one
that matters most, Huang et al.'s finding that **stronger-reasoning models are worse at temporal
applicability** because they collapse onto "apply the current law". A critic that shares that bias
does not catch a stale-law answer; it ratifies it, and adds a confidence signal on top.

The E3→E6 cascade is the same idea done deterministically. It is readable, testable, explainable to a
regulator, and each stage was built against a measured error bucket (`eval_taxonomy.py`:
wrong_binding n=45, paraphrase n=17, dropped_qualifier n=9). Multiply that by cost: a critic loop is
2-4× model calls per claim against an all-time inference spend of **₹0.00**, for a component whose
own literature says it inherits the bias it is deployed to catch.

**Verdict: refuse. Adopt the pattern's *intent* — a stage whose only power is to refuse — which is
already `metric_policy.MODULE_ROLES["E6"] = GATE`.**

### 3.3 Parallel-agent fan-out over 100,000 documents — ANTI-PATTERN, decisively

Take the claimed ceiling at face value purely as arithmetic. At a conservative 5,000 tokens per
document, one pass over 100,000 documents is **500 M input tokens**. At $1/M — cheap for any model
capable of legal analysis — that is **~$500 per run**, ~₹44,000, before output tokens, before
retries, before the multi-agent multiplier that the same claim implies.

Against: all-time inference spend on this project is **₹0.00**, and `docs/PROVIDER_DECISION.md`
measured that a single 7,400-token answer does not fit inside one minute of a free-tier budget.

But cost is the second objection. **The first is that the target user does not have 100,000
documents.** An Indian solo or small corporate practice reviewing a board resolution, a notice, and a
set of minutes is working with single-digit to low-hundreds documents per matter. Building
fan-out infrastructure for a document volume the segment does not produce is building for a
different customer.

**Verdict: refuse. The scale axis for this product is rules-per-document, not documents-per-matter
(§4.4).**

### 3.4 Certification (SOC 2 Type II / ISO 27001) — not an anti-pattern, a **sequencing error** if done now

No arithmetic is offered here because we hold no verified figure for audit cost, and inventing one
would repeat the error this document exists to catch. The sequencing argument stands without it:

certification is a **sales unlock for buyers with a procurement function**. `docs/PERSONAS.md` splits
buyer from user and notes they *converge for the independent advocate* — who has no vendor security
review to pass. `docs/CLAIMS_LEDGER.md` records **zero corporate lawyers have reviewed the system**
and classes customer validation UNVERIFIED. Certifying a pre-validation prototype spends the scarcest
resource on the objection of a customer we have not yet met.

**Verdict: defer, deliberately, and record the trigger** — the first buyer with a security
questionnaire. Meanwhile the underlying *substance* (don't retain what you don't need, don't obtain
private documents, fail closed) is already policy in `CLAUDE.md` and `checker/robots.py`, and is
worth stating publicly as a plain-English commitment long before any certificate exists.

### 3.5 Partner-authored golden datasets as a prerequisite — ANTI-PATTERN *as a gate*, correct as a goal

Requiring senior-lawyer-authored eval data before building is a blocker misdiagnosed as a
requirement — it makes progress contingent on a relationship we do not have, and
`docs/EVIDENCE_PROTOCOL.md` deliberately retired exactly this kind of gate ("30 practising-CS
interviews before proceeding"). The protocol's answer is Tier 1: *"Buildable now, no humans needed."*
And `entail_mine.py` demonstrates it — the corpus is a labelled entailment set whose labels are
**correct by construction** rather than by anyone's judgement.

**Verdict: build the constructed benchmark now; keep Tier 5 lawyer review as a gate on *claims*, not
on development.** That is already the protocol; this section exists only to stop the competitor
framing re-importing the blocker.

---

## 4. Structural assumptions that do not hold for an Indian solo / small corporate practice

Both products, as described, are built for a large Anglo-American firm. Each assumption below is load
bearing for them and false for our stated persona (`docs/PERSONAS.md`: corporate advocate,
independent or small firm; in-house counsel).

### 4.1 A document management system exists

DMS integrations (Box / iManage / NetDocuments) and Word/Outlook add-ins presuppose an IT estate: a
DMS licence, managed Office deployments, and an administrator able to approve an add-in. The Indian
solo practice's document system is a laptop folder, Gmail attachments, WhatsApp, and possibly Google
Drive — with the document arriving as a **scanned PDF or a photograph of a signed page**, not as a
`.docx` with tracked changes.

*Consequence for us:* the integration surface is not the one described. It is upload-and-share, and
`checker/pdf_text.py` / `pdf_signature.py` / `doc_verification.py` are the right investments —
including the case the Anglo-American products barely need, an image-only scan. **Building a Word
add-in for this segment is building for the wrong desk.**

### 4.2 A firm playbook exists

"Compare this contract to our standard position" requires a written house position to compare
against. A large firm has one; a solo advocate does not — and does not want to buy a product that
first asks them to author one.

*Consequence for us, and it is the strategically important one:* **our benchmark is the statute, not
the firm's precedent.** The standard is the Companies Act, SS-1/SS-2, and the Gazette — public,
citable, and identical for every customer. That inverts the economics: playbook products must be
configured per customer before they produce value; a statute-benchmarked product is valuable on
first use with zero configuration. This is a genuine structural advantage of the Indian
corporate-compliance wedge and it should be stated as one.

### 4.3 A data room exists, and the work is many-documents-one-question

Tabular review over a data room assumes an M&A or diligence shape: hundreds of near-identical
instruments (leases, NDAs, employment contracts) where the unit of work is *the same question asked
of every document*. That is a large-firm transactional workload.

*Consequence for us:* the volume is not there, so the feature's economics are not there.

### 4.4 The natural grid is transposed

This is the most useful thing in the whole competitive read, and it is a *design* insight rather than
a competitor fact.

Their grid is **documents (rows) × questions (columns)** — 400 leases, "what is the break clause?"

Ours is **one document × many rules** — one board resolution against s.173, s.174, s.179, SS-1, and
the effective-date question for each. The scaling axis is rules-per-document, not
documents-per-matter.

The *pattern* (a traceable grid of cells, each anchored to its evidence) transfers completely. The
*axes* do not. `checker/review_table.py` already builds our shape — claim × qualifier, with
PRESERVED / MISSING / NOT_APPLICABLE per cell and the premise underneath. Turning that into the
user-facing surface for a client document is a small, well-scoped piece of work with no new
dependency, and it is the single highest-leverage borrowable idea in the input document.

### 4.5 Ground truth is private; ours is public

Their correctness is judged against a client's own prior deals and a partner's judgement — private,
unauditable from outside, and therefore commercially safe to be wrong about quietly.

Ours is judged against the Gazette and India Code. **Every error we make is publicly checkable by
anyone with a browser.** That cuts both ways and both directions matter:

- *Liability:* we cannot hide a wrong citation behind confidentiality. This is why
  `claim_verifier.py` refuses to emit `SUPPORTED`, why `docs/RETRACTIONS.md` exists, and why the
  fabricated-case-citation scenario in `docs/LEGAL_AI_ARCHITECTURE_ANALYSIS.md` §1.1 is treated as
  existential rather than embarrassing.
- *Moat:* a public benchmark is a benchmark a customer can run themselves. "We hold statute only, no
  judgments" is checkable in a way no playbook-benchmarked claim can be. That checkability is the
  asset.

### 4.6 The law is a stable background

Anglo-American document-review products treat the statute as a fixed backdrop and the document as the
variable. The Indian corporate position is the reverse: the amendment ledger holds **451 records**,
`docs/TEMPORAL_PROOF.md` proves boundary behaviour across amendments to s.177, s.447 and s.35, and
Cymbler et al. measured **static RAG retrieving the date-applicable version 0% of the time**.

**Not one feature in the input document addresses point-in-time statutory correctness.** Whether
that reflects the products or only the document's author, we cannot know. What we can say is that
the axis this project has spent its effort on is not an axis the document describes anyone competing
on — consistent with `docs/MODEL_PLAN.md`: *"Point-in-time correctness is won in the corpus, not the
model."*

### 4.7 Procurement, pricing and language

Zero-data-retention *contractual terms* presuppose a counterparty with a GC and a vendor security
review. A solo advocate has no procurement function but does have a professional confidentiality
duty. The transferable form is therefore **architectural, not contractual**: retain nothing by
default, never obtain private minutes (already `CLAUDE.md` policy), and be able to say so in one
sentence a practitioner can evaluate without a lawyer.

On price: `docs/CLAIMS_LEDGER.md` classes all TAM/SAM figures **UNVERIFIED for lawyers** and
`docs/PRODUCT_SCOPE.md` records that the market model is built on CS anchors and must be rebuilt.
The `$50,000/year` figure that appears in `docs/LEGAL_AI_ARCHITECTURE_ANALYSIS.md` is itself an
unsourced competitor number and should be treated as UNVERIFIED wherever it appears, including
there. **No price comparison should be drawn in either direction until the lawyer-side model is
rebuilt.**

---

## 5. What we could not verify, and what would settle it

**Everything above marked PLAUSIBLE or SUSPICIOUS is unverified.** This section lists what to check
and — more importantly — *what would actually settle each question*, since most of these can be
"researched" indefinitely without ever being resolved.

### 5.1 The decisive check first: H7 (Tenet / Kimi K3)

| Check | Where | What settles it |
|---|---|---|
| Does a Moonshot AI "K3" exist? | The lab's own GitHub organisation and HuggingFace organisation; arXiv for a K3 technical report | **A dated model card or technical report predating the claimed August 2026 release settles existence.** Its absence, given that the prior releases shipped public artefacts, is close to decisive *against*. |
| Did Harvey release a model named "Tenet"? | The vendor's own newsroom/blog, plus one independent trade publication | **Only a first-party announcement naming the base model settles the post-training claim.** A journalist's paraphrase does not — reporters routinely compress "built on" and "fine-tuned from". |
| Is "Asynchronous Reinforcement Learning" the named method? | The same first-party post; arXiv for the specific method name | Nothing short of a first-party technical description settles this. Confirming that async RL *exists* (it does — A3C, Mnih et al. 2016, and modern async RLHF infrastructure) settles nothing about attribution. |
| Licence position | The base model's licence file on its official repository | Determines whether the claim is even permissible as described. A licence forbidding it would be decisive against. |

**Stop condition:** if the model-card check comes back empty, record H7 as **RETRACTED — FABRICATED**
in `docs/CLAIMS_LEDGER.md` and do not revisit. Do not soften to "unconfirmed reports suggest".

### 5.2 Legora

| Check | Where | What settles it |
|---|---|---|
| Corporate identity and the Leya → Legora rename | Swedish company register (Bolagsverket) | Registry filing. Decisive. |
| Feature names ("tabular review", "Workflows") | The vendor's own product pages, and an archived snapshot for the date | A dated page. Decisive for existence; says nothing about implementation. |
| SOC 2 Type II / ISO 27001 | Trust/security page; certificate number; **the accredited certification body's own public register** | **The certification body's register is the only decisive source.** A logo on a marketing page is not evidence — this is exactly the primary-vs-secondary distinction `docs/SOURCE_POLICY.md` enforces on legal sources, applied to vendor claims. |
| DMS integrations, Word/Outlook add-ins | Microsoft AppSource listing; each DMS vendor's own marketplace | A live third-party marketplace listing is better evidence than the vendor's own claim. |
| Design-partner law firm | Press releases from **both** sides | Two-sided confirmation. One-sided is marketing. |
| The "BAR" benchmark | The published methodology, if any | **Two questions, in order: (1) does it publish a majority-class / trivial baseline? (2) does it report abstention rate?** Per `checker/metric_policy.py` and Afane et al. (CSLAW 2026), a benchmark answering "no" to either is uninterpretable and should be recorded as such rather than argued with. |
| The ROI report | The report itself | Method section only. If the counterfactual is self-reported time savings, it is ANECDOTE class regardless of who published it. |
| Architecture claims (L3, L5, L6, L7) | Engineering blog; **conference talks; and job postings** | Job postings are the highest-yield source for stack claims — they name real infrastructure because they must attract people who use it. Even so: **a job posting settles what they hire for, never what the pipeline does.** L7 will most likely remain UNFALSIFIABLE and should be recorded permanently as such rather than left open. |

### 5.3 Harvey

| Check | Where | What settles it |
|---|---|---|
| Founders, founding year | Company about page; incorporation records | Registry. Decisive. |
| OpenAI Startup Fund investment | The fund's own portfolio listing | Portfolio page settles the investment. **Nothing available settles "exclusive"** — record that word as unsupported and move on. |
| "Vault", and any document-count ceiling | Product documentation; pricing/limits page | A documented limit settles the number. Note that a *marketing* ceiling and an *engineering* limit are different facts and the page may only give the first. |
| "Golden datasets", eval gating | Engineering blog; conference talks | Likely to remain unfalsifiable. Doesn't matter — P6 is ours already and stricter. |
| Three-layer stack (H4) | — | **Record as UNFALSIFIABLE and close it.** No public source can settle a private architecture claim, and leaving it "open" invites it to be repeated. |

### 5.4 The general techniques, which need no competitor at all

These are the citations to fetch, because they are what §2 actually rests on, and they are checkable
against primary literature rather than any vendor:

- RAG — Lewis et al., NeurIPS 2020. Dense passage retrieval — Karpukhin et al., EMNLP 2020.
- BM25 — Robertson & Walker 1994; idf — Spärck Jones 1972 (already cited in `checker/retrieval.py`).
- BM25 vs dense on entity-rich exact match — Sciavolino et al., EMNLP 2021 (already cited in
  `docs/NON_GOALS.md`; **fetch and verify the scope of the finding**, since we lean on it hard).
- Neural reranking — Nogueira & Cho 2019.
- Attributed generation / span-level citation — Rashkin et al. 2021 (AIS); Gao et al. 2023 (ALCE).
  **This is P11, our clearest gap.**
- Self-correction loops — Self-Refine (Madaan et al. 2023), Reflexion (Shinn et al. 2023), CRITIC
  (Gou et al. 2023), Self-RAG (Asai et al. 2023). Note `docs/TECHNICAL_PLAN.md` already flagged a
  "Self-RAG reduces hallucination by 40%" claim as unverified-as-stated — **re-read the paper's
  actual reported gains before anyone cites a number.**
- Asynchronous RL — A3C, Mnih et al., ICML 2016, plus current async RLHF/RLVR infrastructure work.
- The legal-AI evaluation literature this repo already depends on and should hold copies of:
  Magesh et al. (hallucination in commercial legal research tools; refusal of LLM-as-judge),
  Cymbler et al. 2026 (static RAG at 0% on date-applicable versions), Huang et al. 2026
  (stronger reasoners worse on temporal applicability), Afane et al. CSLAW 2026 (all-affirmative
  baseline F1 0.73). **Several are cited across our docs without a copy in the repo. Fix that
  before any of them appears in an external claim.**

### 5.5 Ceiling on what verification can ever buy us

Recorded so nobody spends a week on this expecting more than it can give.

Even fully verified, competitor internals sourced from marketing pages, blogs and job postings are
**VERIFIED_SECONDARY at best**, never VERIFIED_PRIMARY, and vendor-run benchmarks are
**ANECDOTE-class** because we cannot reproduce them. Under `docs/EVIDENCE_PROTOCOL.md` that permits
internal reasoning and forbids external assertion.

The strategically honest conclusion: **the input document contained no engineering pattern this
project cannot build, and no evidence about whether anyone will pay for it.** `docs/CLAIMS_LEDGER.md`
records the binding constraint — **zero corporate lawyers have reviewed the system**. Time spent
verifying a competitor's architecture is time not spent on Tier 1 (the constructed benchmark,
buildable now, no humans needed) or Tier 5 (the one practising-lawyer review that gates every claim
we want to make). Both of those are on the critical path. None of this is.

---

## Ledger entries proposed

For `docs/CLAIMS_LEDGER.md`, if and when these are ever discussed outside this file:

| Claim | Evidence | Class | Safe wording |
|---|---|---|---|
| Competitor A did not train a foundation model | None held | UNVERIFIED | *(do not use)* |
| Competitor B released a proprietary model post-trained from a third-party base, Aug 2026 | None held; seven fabrication markers (§1.3) | **UNVERIFIED — treat as likely fabricated** | *(do not use, not even hedged)* |
| Competitor products use RAG with hybrid retrieval | Technique is published (Lewis 2020, Robertson 1994); attribution unsourced | UNVERIFIED as attribution | "hybrid sparse/dense retrieval is standard practice in the category" — with no company named |
| Competitor holds SOC 2 Type II / ISO 27001 | None held; settleable from a certification body's register | UNVERIFIED | *(do not use until the register is checked)* |
| Competitors do not address point-in-time statutory correctness | Absence of evidence in an unsourced document | **UNVERIFIED — absence of evidence only** | "we have not established that any competitor addresses point-in-time correctness" — never "no competitor does" |

That last row is the one most likely to be misused in our favour, so it is written out explicitly.
An unsourced document's silence about a feature is not evidence that the feature is missing.
