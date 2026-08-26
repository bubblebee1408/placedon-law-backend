# AI model plan — what we run, what we train, what we refuse

## The decision the research already made for us

Three measured findings constrain every choice below:

1. **Static RAG retrieves the date-applicable statutory version 0% of the time**
   (Cymbler et al. 2026, 32,436 versioned articles). Point-in-time correctness is
   won in the corpus, not the model.
2. **Stronger-reasoning models are *worse* at temporal applicability** (Huang et
   al. 2026) — they collapse onto "apply the current law".
3. **LLM-as-judge is unsafe here.** Magesh et al. refused it outright; Cymbler et
   al. used deterministic regex nuggets because an LLM judge inherits the same
   recency bias it is meant to detect.

So: **we are not training a foundation model, and the LLM is the least trusted
component in the system.** Our moat is statutory currency and the admission
gate. A better model does not close that gap and a worse one does not open it.

## Model selection

| Job | Model | Why | Licence |
|---|---|---|---|
| **Applicability, dates, in-force** | **No model.** `checker/admission.py`, `as_of`, `derived_date` | Deterministic. This is the product. A model here is a regression | — |
| **Document authenticity** | **No model.** `checker/pdf_signature.py` + `trust.py` | Cryptography decides. No hallucination surface | — |
| Retrieval + rerank | **InLegalBERT** (`law-ai/InLegalBERT`) | Pretrained on ~5.4M Indian legal docs; small, cheap, runs on CPU | **MIT** — commercially clean |
| Claim–source entailment | Fine-tuned NLI head (see below) | The missing link. Deterministic checks cannot judge paraphrase | ours + CC-BY data |
| Drafting language | Claude (Sonnet tier) via API | Only ever rewrites text already admitted. Never decides applicability | commercial API |
| Evaluation | **No model.** Deterministic fixtures | Per Magesh and Cymbler. An LLM judge is not evidence | — |

**The generation contract:** the model receives only admitted evidence and may
only produce language entailed by it. It never selects authority, never decides
whether a provision applies, and never supplies a date. Those come from code that
can be read and tested. This is already how `checker/model_adapter.py` is shaped —
shadow mode, fail-closed parsing.

## The actual gap: entailment

`GROUNDED` cannot pass for any case today. We can check that a citation exists, is
admitted, and is in force. We cannot check that the sentence we produced *follows
from* the text we served. Magesh et al. found **inapplicable authority contributes
to 23-38% of hallucinations** — a verifier that only checks existence catches
almost none of it.

This is the one place where a trained model earns its place, and it needs labelled
data we do not have.

### Where the labels come from — we already own them

Our corpus is a labelled entailment set nobody has mined:

- **Positive pairs**: `(section text, its own amendment footnote claim)` — 434
  parsed amendment records, 24 independently corroborated against the amending Act.
- **Hard negatives, and this is the valuable part**: the *prior* wording of an
  amended span vs the *current* text. Semantically near-identical, legally
  opposite. A model that cannot separate these is exactly the model that serves
  repealed law as current — the failure Huang et al. measured.
- **Date negatives**: same claim, wrong as-of date, generated from `timeline.py`.
- **Instrument negatives**: `ACT:...:S56` vs `RULE:...:R56` from `legal_ref.py`.

Supplement with **ContractNLI** (CC-BY-4.0, commercially clean) for general legal
NLI shape. Do **not** touch ILDC, HLDC, IL-TUR or Pile of Law — all non-commercial.

### Accuracy, measured honestly

Following Magesh et al.'s protocol, not their numbers:

- Preregister the question set before running anything.
- Code **two axes**: correctness *and* groundedness. `hallucinated = incorrect OR
  misgrounded` — a right answer citing unsupporting authority is still a failure.
- Report inter-rater agreement (κ) on a re-coded sample.
- **n must be large enough to resolve the claim.** 100 samples cannot measure 2%
  (95% CI ≈ 0.2-7%). Bounding 2% to ±1% needs ~750+.
- Never report a number produced by an LLM judge.

## Backend architecture

Unchanged in shape, because it is already right:

```
question + as-of date
  → retrieval            (InLegalBERT rerank over the admitted corpus)
  → admission gate       (SERVABLE_STATES; refuses rather than guesses)
  → as_of reconstruction (versioned text; UNVERIFIED at section level today)
  → generation           (Claude, from served evidence only)
  → entailment check     (THE GAP — every claim must follow from served text)
  → attribution ladder   (RETRIEVED→ADMITTED→SERVED→CITED→GROUNDED)
```

Deferred until a user complains: Neo4j, Pinecone, Elasticsearch, Celery. The repo
has zero third-party dependencies and does this today.

## On "what Claude did inside"

I do not have visibility into Anthropic's internal legal tooling and will not
guess at it. What is publicly established is the architecture above: constrain the
model with retrieved authority, verify attribution, and abstain. Our differentiator
is not a better model — it is the versioned Indian statutory corpus, which the
literature confirms does not exist for any Indian Act.
