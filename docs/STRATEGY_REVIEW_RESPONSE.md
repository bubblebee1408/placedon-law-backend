# Response to the multi-agent strategy review

A long external analysis (three-agent: champion / devil's advocate / reality
checker, plus a defensibility framework) was run against this project. This is
the response, written to be argued with. It does three things: corrects the
factual claims about the codebase, keeps what the analysis gets right, and flags
where its central recommendation collides with rules this project holds
non-negotiable.

Written 2026-09-04, against commit history verifiable in the repo.

---

## 1. The factual record

The analysis is working from a stale snapshot, and several load-bearing claims
are wrong. Each below is checkable from the repo.

| Claim in the analysis | What the repo shows |
|---|---|
| "12 strategy docs vs **1 backend code commit**"; "planning theater"; "founder procrastination disguised as strategy" | **101 code commits** on this branch (feat/fix/refactor), 238 commits total |
| "S.96 is a **50-line date script**"; "hardcoded if/else will collapse under Sections 185, 186, 188" | **8 registered obligations**, including a *disjunctive* threshold (s.135) and a *conjunctive* one (s.2(85)), each surfacing its provisos through the `Obligation`/decider pattern. The collapse it predicts is the exact failure that pattern exists to prevent, and it is holding across eight sections. |
| "the product lacks an API, a database, or authentication" | An HTTP surface exists: `checker/matrix_view.py` + `scripts/serve_matrix.py`, zero-dependency. No DB or auth yet — that part is true. |
| "35 test suites" | 67 suites in `scripts/run_tests.sh` |
| "**₹2.91** per answer" as a unit-cost benchmark | Never a production COGS figure. The deterministic path is ₹0; the extractor is ~₹0.38 measured. Multi-tenant cloud COGS (DB, auth, OCR, PDF) is genuinely unmeasured. The analysis is right to call ₹2.91 fiction *if presented as production cost* — so this document does not present it as one. |

The "planning theater" charge is the one to reject outright. It is false, and
acting on it — freezing the docs and panic-building — optimises against a
problem that does not exist.

## 2. What it gets right, and should be kept

- **Buyer is not user.** The CFO/GC holds the budget; the Company Secretary
  feels the exposure. Real, and already recorded in our own docs as `R-011`.
- **The seasonality churn cliff.** Companies Act work is Jul–Oct heavy; eight
  months are quiet. Unaddressed, and a genuine retention risk.
- **The artifact gap.** A matrix that only says "you are in breach" is worth
  less than one that also produces the fix. Fair.
- **"Negative compliance" — the missing document is the finding.** The analysis
  presents this as a gap Placedon must build. It is **already what
  `checker/obligations.py` does**: rows are generated from the law, not from
  uploaded documents, so a company that has filed nothing still gets a full
  matrix. The analysis independently reinvented the core thesis and mistook it
  for a gap. That is strong external validation of the architecture, and it is
  worth noticing that a skeptical outside read arrived at the same design.

## 3. Where it is dangerous

Three of its recommendations collide with rules this project holds
non-negotiable. These are not style disagreements.

### 3.1 "Enterprise Risk Insurance" and "guaranteed zero statutory defects"

The single most dangerous phrase in the document. This project is not an
insurer, cannot indemnify, and **no lawyer has validated a single output**. A
deterministic engine on an incomplete corpus can guarantee it did not contradict
itself. It cannot guarantee zero defects — that is a claim about a completeness
it does not have. `CLAUDE.md` forbids unsupported claims precisely here, and
"director liability insurance" is itself a representation that could create
liability. **Reject the framing; keep the use case** (pre-diligence assurance)
with wording that says what the tool actually establishes.

### 3.2 Generating ready-to-sign artifacts flips the whole discipline

The architecture is "the model proposes, the system verifies, the reviewer
decides." Generating a ready-to-sign board resolution makes the system **the
proposer of a legally operative instrument.** If it is wrong, the tool drafted a
defective legal document — a categorically larger liability surface than
verifying one. It also runs into `s.52(1)(q)(ii)` (Act text served only with
original matter; never emit bare statutory text) and "never repair a defective
government source." Artifact generation is not off the table, but it is a
governance decision with its own liability analysis, not a feature to slot in.

### 3.3 "Build s.185/186/188 immediately" contradicts itself

Commercially those are the right sections. But the analysis's own pipeline puts
a "Corporate Entity Graph" — shareholding percentages, director interest,
inter-company structure — as the layer beneath them, and **we do not have it**;
it is a large build. Those sections are also blocked on unacquired subordinate
rules (the S-002 class of problem). So "build s.185 now" is the right target and
the wrong next step, by the analysis's own architecture.

### 3.4 The market claims are unverified

SpotDraft / Provakil / Bharat.Law funding, "hundreds of millions in Indian
legaltech," ₹15L–50L ACV, ₹12–30 real COGS: all unsourced. Same discipline as
`COMPETITOR_FEATURE_MATRIX.md` — treat as hypotheses to test, not facts to build
on.

## 4. The synthesis the analysis misses

It frames the choice as *pivot from verify to artifacts*. That is a false
choice, and the honest position sits between:

> **Do not generate legally-operative documents. Generate the one artifact that
> IS the discipline: the dated, cited, source-verified compliance memo.**

The matrix already produces rows carrying provenance, source spans, and a
refusal-when-unsure. Rendered as a **pre-diligence evidence pack** — "here is
this company's Companies Act position on this date, with the Gazette instrument
behind every line, and here is exactly what could not be verified" — that is:

- an **artifact** a CFO hands to diligence counsel (the real use case the
  analysis correctly identified under "The Transactional Due Diligence Freeze"),
- **high-value** for the funding-freeze pain it describes,
- and it needs **no zero-defect guarantee, no drafting of operative
  instruments, and no claim the tool cannot defend.**

It is the artifact that lives *inside* the moat rather than trading it away. The
genuinely valuable insight across all four agents is the **pre-diligence audit**
use case. The "insurance" pitch and the ready-to-sign drafting are the parts to
leave.

## 5. What actually settles this

Every open question in that entire document — is the artifact gap fatal, will a
CFO pay, is refusal a feature or a churn driver, is the pre-diligence framing
right — is answered by the same thing, and it is not more analysis:

**One practising Company Secretary, twenty minutes, the validation kit.**

`docs/H001_OUTREACH.md` and the kit are built and ready. That is the standing
recommendation, unchanged by a fifth strategy document, including this one.
