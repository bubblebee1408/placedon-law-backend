# 04: The mathematics and algorithms, with proofs where they are short enough to check

**What this section claims, and does not.**

- Every result here is either a known theorem applied to our setting, with the source named, or
  an elementary lemma proved in full.
- **None is claimed as new mathematics.** What may be new is the application. For example, we
  have not found provenance semirings used to carry legal evidence states. But no systematic
  literature search has been done, so that is **[OPEN]**, not a claim.
- Every number was recomputed on 2026-09-25 with `python3` and, where one exists, the repo's own
  function.

Notation: E is the evidence chain, ν assigns an evidence state to each base fact, and a
*derivation* is a positive AND/OR formula over base facts.

---

## 1. The evidence chain

`checker/provenance.py:40` [R] declares
`STATES = (UNRESOLVED, INFERRED, UNFETCHED_CORROBORATION, CORROBORATED, VERIFIED, RETRACTED)`.
That tuple is **a vocabulary, not an order**: RETRACTED is last, yet it is the weakest. The
algebra below needs a declared total order. The proposal is:

```
RETRACTED  <  UNRESOLVED  <  INFERRED  <  UNFETCHED_CORROBORATION  <  CORROBORATED  <  VERIFIED
   (⊥)                                                                                   (⊤)
```

**[OPEN], and a decision for the legal-verifier subagent, not an engineer:** is an inaccessible
source "reported to agree" (UNFETCHED_CORROBORATION) really stronger than our own inference
(INFERRED)? The algebra works for any total order. The legal meaning depends on which one is
chosen. The order is declared once, as a `lattice.Lattice` [R], so `rank()` raises on anything
outside it.

## 2. Evidence states form a semiring, so revocation is re-evaluation

**Theorem 1.** Let (C, ≤) be a finite chain with least element ⊥ and greatest element ⊤. Then
(C, max, min, ⊥, ⊤) is a commutative semiring. It is idempotent (max(a,a) = a) and absorptive
(max(a, min(a,b)) = a).

*Proof.*

1. max is associative and commutative, and ⊥ is its identity, because ⊥ ≤ a for all a.
2. min is associative and commutative, and ⊤ is its identity.
3. ⊥ annihilates: min(⊥, a) = ⊥.
4. min distributes over max, because every chain is a distributive lattice. Directly: for
   a, b, c ∈ C, compare b and c. Without loss of generality b ≤ c. Then max(b, c) = c, so
   min(a, max(b,c)) = min(a,c). And min(a,b) ≤ min(a,c), so max(min(a,b), min(a,c)) = min(a,c).
5. Idempotence is immediate.
6. Absorption: min(a,b) ≤ a, so max(a, min(a,b)) = a. ∎

This is the "bottleneck" (or fuzzy) semiring. Green, Karvounarakis and Tannen (PODS 2007) [V]
showed the following. For positive queries (no negation), annotating base facts with elements of
a commutative semiring and propagating them through the query commutes with semiring
homomorphisms. So one symbolic provenance expression, evaluated under any valuation, gives the
same result as re-running the query under that valuation.

**Lemma 2 (minimal witnesses suffice).** Let a derivation be a positive AND/OR formula φ over
base facts X. Let Wit(φ) be its set of minimal satisfying sets (the minimal sets of facts which,
if all present, make φ true). Then for every valuation ν : X → C,

```
eval(φ, ν)  =  max over W ∈ Wit(φ) of  min over x ∈ W of ν(x)
```

*Proof.*

1. Distributivity (Theorem 1) rewrites φ's evaluation into disjunctive normal form: a max over
   conjunctive terms of the min over each term's facts.
2. Every term contains some minimal witness W, and every minimal witness is a term's fact set,
   up to subsumption.
3. Take a term T ⊇ W. Then min over T ≤ min over W. By absorption, max(min W, min T) = min W,
   so non-minimal terms can be dropped without changing the result.
4. Idempotence removes duplicate terms. ∎

**Corollary 3 (monotonicity).** If ν ≤ ν' pointwise, then eval(φ, ν) ≤ eval(φ, ν').
*Proof:* min and max are both monotone in each argument. ∎

In words:

- **Attesting a source can never weaken any conclusion.**
- **Retracting a source can never strengthen one.**

This is a property-based test, not a comment. `derivation._test()` draws random derivations and
valuations and checks the implication.

**Corollary 4 (incremental revocation).** When ν(x) changes, only conclusions with x in some
witness set can change, and each is recomputed in O(Σ|W|) over its own witness sets. No query is
re-run and no document is re-read.

**What this buys the product.**

- Today, when an instrument is retracted, nothing tells us which served answers rested on it.
- With `derivation.dependents(x)`, it is a lookup. With the observation store's `known_at`
  (§3), we can also answer *"which answers we gave last month rested on it"*.
- **That is the recall notice a law firm needs**, and no product we have examined ships it. That
  is [I]: an absence found in `docs/research/CONNECTORS_AND_THE_WHITE_SPACE_2026_09_25.md` for
  Harvey and Spellbook, not a market-wide search.

**Two limits, stated so nobody builds past them.**

1. **Negation is not covered.** "Applies *unless* exempt" is not positive, and semiring
   provenance for negation is a harder, different theory. **The workaround:** make "exemption
   does not apply" a base fact of its own, with its own evidence state. Under the tri-state rule
   (§3) it is NO only when a completeness assertion backs it; otherwise UNKNOWN, which is
   `UNRESOLVED` evidence.
2. **OR is sound only between derivations of the same value.** max says "one good derivation
   suffices". That is true only if both derivations conclude the same thing. Conflicting values
   are `SOURCE_CONFLICT` [R: `provenance.py:160`] and are refused (03 §4).

## 3. Tri-state answers stay sound across two time axes

`entity_graph.py:14-20` [R] answers existence queries YES, NO or UNKNOWN. NO is given only under
an explicit completeness assertion. This extends that rule to bitemporal data and proves the
property the audit trail depends on.

**Setup.**

- Each edge e and each completeness assertion c carries a valid interval and a `known_at`.
- G_k is the set of edges with known_at ≤ k, and C_k the set of assertions with known_at ≤ k.
- The query Q(a, r, t, k) asks: is there an r-edge from a, valid at t, as known at k?
  - It returns **YES** if some edge in G_k matches and is valid at t.
  - It returns **NO** if no edge matches and some c ∈ C_k asserts completeness of (a, r, OUT)
    at t.
  - Otherwise it returns **UNKNOWN**.

**Theorem 5 (soundness).** Suppose every edge in G_k that is valid at t is true of the world at
t, and every assertion in C_k that covers t is true at t. Then YES implies the relationship held
at t, and NO implies it did not.

*Proof.*

- YES exhibits an edge in G_k valid at t. By hypothesis it is true.
- NO holds only under an assertion that G_k contains every true r-edge from a at t. No such edge
  is in G_k, so none is true. ∎

UNKNOWN makes no claim, so it cannot be wrong. It can only be unhelpful, and that is measured
separately as coverage.

**Theorem 6 (replay).** If the store is append-only (nothing is deleted, and a correction is a
new row with a later `known_at`), then for every k' > k, computing Q(a, r, t, k) at time k' gives
the same answer as computing it at time k.

*Proof.* Q reads only G_k and C_k. Append-only storage means rows added after k have
known_at > k, so they are excluded, and no row with known_at ≤ k is ever removed or altered. The
inputs are identical, so the outputs are. ∎

The same argument applies to `derivation.evaluate` when ν is read as-known-at k. **This is the
property that lets Themis answer "what did you tell us on 31 March, and why?"** It holds only if
the store never updates in place. That is why 03 §3 forbids it, and why the test for Theorem 6 is
a gate test.

## 4. Impact propagation without deletion

Alerts are reachability from a changed observation to a subscribed target over typed edges
(03 §5). Insertions are maintained incrementally in the semi-naive style: only paths through the
new observation are explored.

The known hard case for incremental view maintenance is deletion. It needs delete-and-rederive
(DRed; Gupta, Mumick and Subrahmanian, SIGMOD 1993, cited from knowledge and not re-checked).
**Our design never deletes.** A retraction is a new observation whose evidence is ⊥. So the
*structure* of reachability only grows, and a retraction changes only the *evidence* on existing
paths. Corollary 4 recomputes that evidence locally.

So the watch engine needs semi-naive insertion plus semiring re-evaluation, and never DRed. That
simplification is a direct consequence of append-only storage [I; the argument above is the
proof].

**Consistency check (nightly):** a full recompute from an empty state must equal the incremental
state exactly. Any difference is a defect, never a tolerance.

## 5. The false-alarm budget

**Deterministic alerts.** A deterministic alert is wrong only if some edge on its path is wrong.
Take a path of edge types 1…L with per-type error rates ε_i. By the union bound, which needs **no
independence assumption**:

```
P(alert is false)  ≤  Σ_i ε_i
```

We do not know ε_i. We can bound it from a human audit: n edges of that type are sampled and
checked, and k are found wrong. We use the Wilson upper bound, as the gold set does.

| Audit result | Wilson 95% upper bound on ε | Consequence for a 3-edge path |
|---|---|---|
| 0 wrong of 59 | 0.0611 | ≤ 0.183, too loose to promise anything |
| 0 wrong of 73 | ≤ 0.05 | ≤ 0.15 |
| 0 wrong of 189 | ≤ 0.02 | ≤ 0.06 |
| 0 wrong of 227 | ≤ 0.0167 | ≤ 0.05 |

**Reading:** to say "at most 1 in 20 of these alerts is false" for a 3-hop alert type, each edge
type needs about **227 audited edges with zero errors**. That is the size of the human audit
G3's exit gate requires. Until it exists, alert precision is reported as the per-type counts, not
as a rate.

**Statistical alerts** (for example, "an unusual number of charge filings"). With M monitored
series each tested at level α per period, the expected number of false alarms is Mα:

- 10,000 × 0.01 = **100 per period**;
- 10,000 × 0.001 = 10 per period.

A lawyer who gets 100 false alarms stops reading alerts. So:

- statistical alerts are **off by default**;
- if one is ever enabled, it is under a false-discovery-rate procedure (Benjamini–Hochberg 1995,
  or Benjamini–Yekutieli 2001 under arbitrary dependence; cited from knowledge and not re-checked);
- it is shown as `SIGNAL`;
- it is gated by `calibration_contract` [R], so no number renders without a track record.

## 6. Entity resolution: Fellegi–Sunter, which proposes and never decides

Fellegi and Sunter (JASA 1969) gave the canonical model [V via Splink's documentation]. For
comparison field k:

- m_k = P(agree | same entity);
- u_k = P(agree | different entities);
- an agreement adds log₂(m_k/u_k) to the match weight;
- a disagreement adds log₂((1−m_k)/(1−u_k)).

The m and u parameters are estimated by EM without labels. The FS decision rule has three
regions (link, possible, non-link), set by two thresholds.

**Our change: there is no automatic "link" region.**

- Weights only rank proposals for the review queue.
- A link becomes a SERVABLE edge only by exact identifier (CIN, LLPIN, DIN) or by human
  attestation.

**The asymmetry that sets the lower threshold.** For sanctions and s.188 counterparties, the
costly error is the **missed** match, not the false one. A false proposal costs a reviewer a
minute. A missed sanctioned party costs the client. So the discard threshold is set for recall,
measured on a labelled set of known true matches. **[OPEN]: we hold no such set.** Building it is
G6's first task.

Indian names add transliteration variance (Mohammed, Mohd., Muhammad), patronymic order and
initials. That is **[I]**, and it is why FS weights are estimated on Indian data, never taken from
a UK or US default.

## 7. Why judgment prediction is not built

The request was to put judgment prediction "behind the harness". The harness is exactly what
says no. There are five independent reasons, each sufficient alone:

1. **Most published "prediction" does not predict.** Medvedeva and McBride (NLLP 2023) [V]
   reviewed over 150 legal-judgment-prediction papers. They found about **7%** actually forecast
   an undecided case. The rest classify the outcome from the text of the judgment that decided it.
2. **The best Indian benchmark is that kind of task.** ILDC (Malik et al., ACL 2021) [V, abstract]
   reports about 78% for the best model against about 94% for experts. The inputs are Supreme
   Court judgments with the decision removed: facts **as written by the court that decided them**
   **[I: consistent with (1); confirm by reading ILDC in full]**. A forecast would need the filings
   before judgment. For our buyer's forum (NCLT and NCLAT), those are closed to machine access
   [R: DATA_ACCESS §5].
3. **The data cannot support a calibrated number.**
   - `calibration_contract.n_min(0.5, 0.05)` returns **256** resolved cases for one stratum. That
     is recomputed here. PLAN_14 §5.2 prints 255, which is the normal approximation; the module's
     exact search gives 256.
   - Stratify by forum × issue × statute at a modest 50 strata, and that is **12,800** resolved
     cases, split by filing date so the test set is truly future.
   - No such corpus is lawfully available for NCLT.
4. **The direction of regulation.** France's Loi n° 2019-222, art. 33 [V] prohibits reusing
   judges' identity data to evaluate, analyse, compare or predict their professional practices,
   under criminal penalty. India has no known equivalent **[OPEN]**. This is a risk, not a rule
   that binds us.
5. **It is off-wedge.** An in-house team asks "are we compliant, as of this date, on what basis?",
   not "will we win?" (PLAN_16 decision 1; `CLAUDE.md` scope).

**What is built instead** is the citator (03 §8). It answers the question a litigator really
needs from a legal-intelligence tool: *is the authority I rely on still good?* Deterministically,
with the witness.

## 8. Neural networks: what to train, when, and on what

**No foundation model** (`CLAUDE.md`). There are three small models, each gated by the arithmetic
below and each **proposing only**.

| # | Model | Before a model is allowed | Labels needed |
|---|---|---|---|
| N1 | Cross-encoder reranker for statutory retrieval | **A deterministic abbreviation lexicon first.** 19 of 22 practitioner abbreviations (AGM, MD, KMP, RPT, …) retrieve nothing (local gold-set run, 2026-09-25). The statute's own definitions (s.2) and headings supply most expansions. A model is trained only if the lexicon's measured gain falls short | HUMAN question→provision pairs, on a held-out split |
| N2 | Citation-treatment classifier (InLegalBERT encoder [V]) | Citation extraction measured first (03 §8) | HUMAN treatment labels |
| N3 | Document-type classifier refinement | `checker/classify.py` [R] measured on the real test corpus first | HUMAN labels on `corpus/testdocs/` |

**The gate on "it got better".** A change is compared with the incumbent on the same questions.
The test is McNemar's paired test on discordant pairs. With discordance rate ψ (the share of
questions where exactly one system is right) and true gain δ, α = 0.05 two-sided and 80% power,
the required n (Connor's approximation) is:

```
n  =  ( z_{α/2} √ψ  +  z_β √(ψ − δ²) )²  /  δ²
```

| ψ | δ | n required |
|---|---|---|
| 0.10 | 0.05 | **312** |
| 0.30 | 0.10 | 234 |
| 0.20 | 0.10 | 155 |
| 0.10 | 0.10 | 77 |

**Reading:**

- The gold set holds 73 entries, of which 33 are MECHANICAL and scoreable, and none are HUMAN.
  **No retrieval or model change can be declared an improvement on it today** unless the gain is
  about 10 points with low discordance, and even then only on a split it was not tuned on.
- This is why the retrieval relaxation of 25 Sep was reverted rather than tuned (local session,
  `RETRIEVAL_DEFECT_2026_09_25`, not yet on `main`).
- The rule: **tune on a dev split, and test once on a frozen test split whose hash is committed
  before the first run.** A test split consulted twice is a dev split.

**Training data rules, unchanged.**

- HUMAN labels only. SYNTHETIC entries may never carry an answer key (`eval/goldset/__init__.py`)
  [R].
- `annotation.to_sft()` must be fixed (`CLAUDE.md` E6) before any training path opens.
- No client document is used without the per-matter opt-in of PLAN_16 decision 3.

## 9. Certification under a changing law

PLAN_18 §2.7 ships conformal certification **disabled**. One reason it must stay so is not yet
written down anywhere, so it is written here.

Split conformal guarantees rest on exchangeability. **An amendment breaks it.** Labels collected
before G.S.R. 880(E) took effect are not exchangeable with questions asked after. Adaptive
Conformal Inference (Gibbs and Candès, NeurIPS 2021) [V] handles shift by updating
α_{t+1} = α_t + γ(α − err_t). It guarantees long-run coverage whatever the data process.

The bound, as transcribed from Proposition 4.1, is **|mean error − α| ≤ (max(α₁, 1−α₁) + γ)/(γT)**.
**[Confirm against the paper before citing.]** At α₁ = 0.1:

| γ | T (labelled answers) | Deviation bound |
|---|---|---|
| 0.005 | 1,000 | 0.181 |
| 0.005 | 10,000 | 0.018 |
| 0.05 | 200 | 0.095 |
| 0.05 | 1,000 | 0.019 |

**Reading:** at the volumes a beta will see, which is hundreds of labelled answers, ACI's
guarantee is either loose (small γ) or bought with a jumpy threshold (large γ). **So the plan is:**

1. Re-calibrate at each amendment boundary, using post-amendment labels only.
2. Refuse certification in each regime until PLAN_16 C1's n is met there.
3. Treat ACI as a research comparison, not the serving mechanism.

## Sources

- Green, Karvounarakis, Tannen, *Provenance Semirings*, PODS 2007, pp. 31–40: https://web.cs.ucdavis.edu/~green/papers/pods07.pdf
- Fellegi–Sunter, via Splink's theory guide: https://moj-analytical-services.github.io/splink/topic_guides/theory/fellegi_sunter.html · https://github.com/moj-analytical-services/splink
- Medvedeva and McBride, NLLP 2023: https://aclanthology.org/2023.nllp-1.9/
- ILDC: https://aclanthology.org/2021.acl-long.313/
- Loi n° 2019-222, art. 33: https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000038261761
- Gibbs and Candès, ACI: https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html
- Adams and MacKay, *Bayesian Online Changepoint Detection*, arXiv:0710.3742, 2007 [V]. Considered for statistical alerts (§5) and **not adopted**: it is the right tool for a single series, and the false-alarm budget binds first.
- InLegalBERT: https://dl.acm.org/doi/10.1145/3594536.3595165
- Cited from knowledge and not re-checked today: Denning 1976; Gupta, Mumick and Subrahmanian 1993 (DRed); Benjamini and Hochberg 1995; Benjamini and Yekutieli 2001; Fellegi and Sunter 1969 (original); Connor 1987 (McNemar sample size).

**Recomputation.** Every table in §5, §7, §8 and §9 was produced by a short `python3` script using
`statistics.NormalDist` and `checker.calibration_contract` (`ece_floor(0.9, 20) = 0.0513`,
`ece_floor(0.1, 6) = 0.1063`, `n_min(0.5, 0.05) = 256`).
