# 05: The lawyer-engineer funnel, and the Labelling Agent that works beside them

**Evidence:** `.claude/loops/…_B_HARVEY_FUNNEL.md` and `…_C_LITERATURE.md` §7. Most
sources are [S]. Anything marked **[I]** is inference.

## 1. Why this is the critical path, not a side project

**Every number Themis may show waits on human labels:**

| What | Labels needed before it can be shown |
|---|---|
| Accuracy of any kind | n ≥ 59 human-checked answers with zero errors bounds the error rate below 5% at 95% confidence (0.95⁵⁹ ≈ 0.048) |
| A conformal singleton at α = 0.05 | ≥ 19 labelled cases per stratum (measured in `conformal._test`) |
| A FORECAST number | a SERVABLE track record (`calibration_contract`) |
| DECLARED → HELD for a body of law | attestation, encoding and a gold set, all by a lawyer |

**Today the gold set holds 0 human labels.**

**How Harvey does it** [S]:

- About 200+ lawyers.
- **Applied Legal Researchers** build and grade evaluations and turn preference votes into
  rankings.
- **Legal engineers** run pilots and adoption.

**Themis needs the first role more than the second** [I]: someone who builds the ground
truth.

## 2. The two roles

| Role | Does | Is not |
|---|---|---|
| **Lawyer-engineer (reviewer)** | Reviews Themis output against the quoted source; decides; writes the reason; builds gold items; attests acquired instruments; checks encodings against the statute | A labeller of anything they cannot cite |
| **Senior adjudicator** | Resolves disagreements; writes the annotation guideline per body of law; signs promotions (DECLARED → HELD, model promotion) | A reviewer of their own first-pass items |

## 3. The funnel: six stages, each with a gate that can be measured

| Stage | Who | Gate to pass (measured, not judged) |
|---|---|---|
| 1. Source | NLU clinics, OpenNyAI-style cohorts, CS and LLB graduates, practising CSs | A written statutory-reading test ≥ 70%: find the provision, the instrument and the operative date |
| 2. Screen | Applicants | 10 gold items answered **with instrument and date cited** |
| 3. Calibration (paid, ~10 h) | Screened applicants | ≥ **80%** agreement with gold (MAUD's lawyer–student level) **and** Cohen's κ ≥ **0.6** on 30 items (above the 0.59 an Indian rhetorical-role corpus reported) |
| 4. Paid pilot | 50 items | The same gates hold, with **10% of items hidden gold** |
| 5. Certified reviewer | Ongoing | Rolling hidden-gold accuracy ≥ 85%, re-tested quarterly |
| 6. Senior adjudicator | 3+ years' practice | κ ≥ **0.8** with other seniors (the ILDC experts reached 0.82) |

**Design rules from the literature:**

- **Prefer pairwise judgements to rubric scores** where the task allows. JudgmentBench:
  pairwise recovered quality ordering at Spearman 0.908 vs 0.150 for rubrics, in 1.92 min
  vs 4.74 min per judgement.
- **Report κ per label family, not one global κ.** Indian legal agreement ranges from 0.65
  (Income Tax) to 0.87 (Competition).
- **One guideline document per body of law**, written by the senior before the first item.
  CUAD used 100+ pages and 70–100 h of training. Themis starts smaller [I].

## 4. The Labelling Agent

**What it is:** a Ring 3 agent with **read-only** access. It sits between the queue and the
reviewer. It **never writes a decision**, and this is enforced by existing code: MCP
exposes no write verb, and `runs.approve` needs an authenticated human key.

| Job | Method | Evidence |
|---|---|---|
| Choose what to label next | Uncertainty sampling: items where the conformal set is {0,1}, or the verifier and model disagree; plus stratified random so the test split stays unbiased | Continuous active learning (Cormack & Grossman) |
| Pre-label | A model proposes a label, shown **greyed**, with the span that supports it | LLM annotators help but score F1 0.54 on statutes (Savelka & Ashley) |
| Earn trust for its pre-labels | The Alternative Annotator Test on a human-labelled subset. Until it passes, pre-labels are hidden on hidden-gold items | ACL 2025 |
| Keep reviewers honest | Inserts hidden gold (10%); computes each reviewer's rolling accuracy and κ; flags drift | — |
| Catch fatigue | Flags decisions made faster than the quote could be read (time on item < reading time of the span) | automation bias (PLAN_23 §1.8) |
| Feed onboarding | Drafts gold items and lexicon entries **from the acquired text of a body of law**, for a lawyer to accept or reject | G0.3 is blocked on exactly this |
| Weak supervision | Regex-style labelling functions for rare defects (for example "resolution passed without quorum") | Snorkel: 2.8× faster model building |

**Where it plugs in** (appendix D §E2):

- a read verb `reviews.next`;
- labels as a view over `decisions ⋈ propositions ⋈ run_steps`;
- migration **007** (`quote_viewed`, `law_versions`, `purpose`, `reviewer_ms_on_item`).

**It depends on F2 being fixed first.** Until then, no `ask` answer has a source to review.

## 5. What it costs to reach the numbers that matter

**Assumptions:**

- 2 independent reviewers × 15 min per item;
- 20% of items adjudicated at 10 min each;
- 10 h of calibration per reviewer;
- a 15-senior-hour gold set.

**Arithmetic checked.** Scenario A: 0.5 h × ₹400 + (2/60) h × ₹1,500 = **₹250 per item**.

| Human-labelled items | Scenario A (reviewer ₹400/h, senior ₹1,500/h) | Scenario B (₹1,000/h, ₹2,000/h) | Reviewers needed (40 h each) |
|---|---|---|---|
| **59** (first bound on the error rate) | **₹45,250** | ₹83,433 | 2 |
| **300** (~1% bound with zero errors; a useful conformal set) | **₹1,13,500** | ₹2,40,000 | 4 |
| **1,000** (PLAN_22 D1's revisit threshold is 1,000+ traces) | **₹3,24,500** | ₹7,26,667 | 13 |

**Pre-funding path [I]:** a research partnership with one NLU (the OpenNyAI/NLSIU model: a
100+ student cohort over a year) for stages 1–4, paid seniors only. That reaches n = 59 for
roughly the senior cost alone. Budget it as **₹25–50k**.

## 6. Legal and ethical limits. Counsel before stage 4

- **Bar Council of India Rule 49** [S]: an advocate who takes full-time salaried employment
  must inform the State Bar Council and cease to practise. Rule 47 bars an advocate from
  personally engaging in business. **Whether part-time contract review triggers Rule 49 is
  OPEN.**
- **Privilege:** *In re Summoning Advocates* (2025 INSC 1275) [S] gives in-house counsel no
  s.132 BSA privilege. [I] Anything a client sends Placedon's reviewers is very likely not
  privileged, so reviewers work on **public material and synthetic matters** until counsel
  says otherwise.
- **DPDP:**
  - s.8(2) requires a processor contract for anyone touching client personal data.
  - Core obligations bind from **13 May 2027** (some sources say the 14th).
  - Whether s.3(c)(ii)'s exemption for "made publicly available" covers MCA filings is
    **OPEN**.
- **The permitted-sources rule** (`CLAUDE.md`) already keeps reviewers on public documents,
  ICSI specimens and public disclosures. The funnel changes nothing there.
