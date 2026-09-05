# Adversarial failure analysis

Written 2026-09-02 against the repository as it stands. This document is written **against** the
project. Where the project is sound it says so in one line and moves on. Everything else is an
attack.

Method: read the constraint set (`CLAUDE.md`), the open ledger (`research/TASKS.md`), the three
planning documents, then the code itself, then **ran** the code to see what it actually emits. Six
of the findings below are reproducible with a single `python3 -c`. Those are marked
**REPRODUCED** and the command is given. A failure that can be demonstrated is worth more than
one that can be argued.

No web search (exhausted). No code was changed.

---

## 0. What this project has already named, so I do not repeat it

Credit where it is due, because it changes what is worth writing. `docs/BUILD_PLAN_PRODUCT.md`
§1.5 already states, in the project's own words, that the product is nearly nonexistent, that
`model_adapter.py` is stubbed, and that two of three benchmark buckets are structurally incapable
of measuring the axis the gate protects. `docs/WORKFLOW_BACKLOG_INDIA.md` §0 already states zero
evidenced frequency, zero CS interviews, the OCR contradiction, and the segment conflict.
`docs/SOURCE_DEFECTS.md` already records SD-001…SD-004 honestly, including one retraction of its
own accusation against a government publisher.

**This is an unusually self-aware repository, and that is itself a hazard.** A project that has
written down its own weaknesses in graded prose has already discharged the emotional cost of
knowing them, without paying the engineering cost of fixing them. Every finding below that
duplicates a known one is marked `[ALREADY NAMED]` and given only the marginal attack — the part
that is *worse* than the version in the docs. The findings that matter are in §7.

---

## Ranked findings

Ranked by (probability × damage). "Probability" is the chance this bites before the first ten
users, not in the abstract.

| # | Finding | P | Damage | Class |
|---|---|---|---|---|
| **F1** | s.96 row renders a real statutory default as green, and a company with no duty yet as red | ~1.0 | Severe | LEGAL |
| **F2** | Client-confidential company financials travel in a GET query string to a third-party host | ~1.0 | Severe | UNNAMED |
| **F3** | The release gate does not score the frozen benchmark (67 rows vs the manifest's 69) | 1.0 (present now) | Severe | UNNAMED |
| **F4** | Human review can only ever produce ENTAILED labels — the single-label bucket is permanent by construction | 1.0 (structural) | Severe | UNNAMED |
| **F5** | The s.173 row can never say "satisfied", and `calendar_year` does not filter meetings | 1.0 (present now) | High | LEGAL |
| **F6** | The matrix presents 4 obligations as a complete matrix of a 529-section Act | ~0.9 | Severe | LEGAL/PRODUCT |
| **F7** | `is_listed` is collected and never used; listed-company obligations do not exist | ~0.7 | Severe | LEGAL |
| **F8** | Budget guard is unenforceable on the declared deploy target, and its failure is written to a list nobody reads | ~0.8 (at Stage 4) | High | UNNAMED |
| **F9** | The moat is asserted over the cheap half of the corpus; 33% of the Act delegates to Rules we hold one set of | ~0.8 | High | STRATEGIC |
| **F10** | The built product is CS work, on the repo's own do-not-build list, in the segment where the incumbent is free | 1.0 (present now) | High | STRATEGIC |
| **F11** | Refusal is the dominant output: 3 of 4 rows are non-answers even when every fact is supplied | 1.0 | High | PRODUCT |
| **F12** | `evidence_pack` refuses to describe itself as point-in-time — the moat cannot reach a user | 1.0 | Medium-High | UNNAMED |
| **F13** | The s.52 copyright guard is a three-string blocklist | ~0.5 | High | UNNAMED |
| **F14** | `prescribed_thresholds` imports from `scripts/` — a packaging bug is indistinguishable from a legal refusal | ~0.5 | Medium | TECHNICAL |
| **F15** | robots fail-closed converts a machine task into an unbounded human queue with no retry | 1.0 (12 days and counting) | Medium | ACQUISITION |
| **F16** | Every s.149 pass is a snapshot claim presented as a period claim | ~0.6 | Medium | LEGAL |

---

## 1. LEGAL failure

The claim under attack: *"The model may propose. The system must verify. The reviewer decides."*
There is no model in Stage 1, so the whole sentence collapses to "the system verifies". It does
not. It verifies **one limb of one subsection** of each of four sections, and reports the result
in a five-state vocabulary that has no state meaning "I checked one limb of five".

### F1 — s.96 is wrong in both directions, and the green one is worse **REPRODUCED**

`checker/obligations.py:186 _decide_agm` decides the **fifteen-month gap limb only**. It says so
in the basis string ("this limb only", line 214). s.96(1) has, on any practitioner's reading, at
least five operative limbs:

1. hold an AGM **in each year** (a calendar-year duty);
2. within **six months** of the close of the financial year (first proviso);
3. **fifteen months** between successive AGMs — the only one implemented;
4. first AGM within **nine months** of the close of the first financial year;
5. the Registrar's extension of up to **three months**, which moves limb 2.

In Indian practice limb 2 is the one that bites. The 30 September deadline is what ROC adjudication
under s.99 is actually about. It is not implemented, and the row does not distinguish "passed"
from "passed the limb I happen to compute".

**Reproduced:**

```
PYTHONPATH=. python3 -c "
from datetime import date
from checker.company_profile import CompanyProfile
from checker.obligations import build, Evidence
p = CompanyProfile(company_class='public', incorporation_date=date(2019,6,1),
    as_of=date(2026,3,31), latest_financial_year='2024-25', is_holding_company=False,
    is_subsidiary_company=False, is_section_8=False, governed_by_special_act=False)
ev = Evidence(agm_dates=(date(2023,12,31), date(2025,1,31)))
print([ (r.state, r.basis) for r in build(p, evidence=ev) if r.obligation_id=='CA13-S96-AGM'])"
```

Output: `APPLIES_SATISFIED`.

That company held **no AGM at all in calendar year 2024** (limb 1 breached) and held its 2024 AGM
four months after the 30 September 2024 statutory deadline (limb 2 breached). Two separate
defaults, each attracting s.99 liability on the company and every officer in default. Placedon
renders the row `APPLIES_SATISFIED`, and `checker/matrix_view.py` paints it with
`.s-APPLIES_SATISFIED{background:#e3f0e9;color:var(--good)}` — **green**.

The "this limb only" caveat is inside the `basis` field, below a green badge, in a UI where the
badge is the only thing rendered in colour and in monospace caps. Nobody reads the small print
under a green light. The project's own defence — that it says which limb it decided — is a
defence of the data model, not of the surface.

Second direction, same function, line 197: `if not ds: return False, "no annual general meeting
was held"`. A company incorporated 10 January 2026, whose first financial year has not yet closed,
telling the form truthfully that no AGM has been held, gets `APPLIES_NOT_SATISFIED` — a fabricated
default. `incorporation_date` is a **required** form field (`matrix_view.py`, "several deadlines
run from it") and `_decide_agm` never reads it. This is the exact error `CLAUDE.md` forbids:
*"Never call a finding a defect when the rule is inapplicable."*

**Detect early:** one test asserting that no row reaches `APPLIES_SATISFIED` while any limb of its
provision is unimplemented; one asserting that no `APPLIES_NOT_SATISFIED` is emitted for a period
in which the duty had not yet accrued.

**Cheapest mitigation:** delete `APPLIES_SATISFIED` from `ROW_STATES` for any obligation whose
`Obligation` record does not enumerate every limb and mark each as implemented or not. Add a
`limbs: tuple[Limb, ...]` field; if any limb is `not_implemented`, the best reachable state is
`APPLIES_UNDETERMINED` with the unchecked limbs listed by name. This is a half-day change and it
converts the single most dangerous output in the product into the product's own thesis.

### F5 — the s.173 row can never pass, and the year is decorative **REPRODUCED**

`checker/s173_slice.py:205-215`: the terminal branch of `review()` sets `status = INDETERMINATE`
even when every finding is satisfied, because quorum is unestablished. There is no path to
`COMPLIANT` for any company that is not a single-director OPC.

`checker/obligations.py:178`: `if r.status == COMPLIANT: return True` — **dead code for every
real company**. So `CA13-S173-BOARD` is structurally incapable of reaching `APPLIES_SATISFIED`.

```
PYTHONPATH=. python3 -c "
from datetime import date; from checker.s173_slice import review, COMPLIANT
r = review(company_class='other', calendar_year=2025, total_board_strength=6,
  meetings=[date(2025,2,10),date(2025,5,5),date(2025,8,20),date(2025,11,25)])
print(r.status, r.status==COMPLIANT)"     # -> INDETERMINATE False
```

A perfectly compliant board year returns INDETERMINATE. The obligations self-test hides this:
`check(b.state in (APPLIES_SATISFIED, APPLIES_UNDETERMINED), "four spaced meetings resolve or
abstain, never fail")` — a disjunctive assertion whose first disjunct is unreachable. **A test
that passes on a dead branch is not a test.**

Worse, and separately: `calendar_year` does not filter the meeting list in the standard regime.
`s173_slice.py:179` counts `len(ms) >= 4` over whatever dates were supplied.

```
PYTHONPATH=. python3 -c "
from datetime import date; from checker.s173_slice import review
r=review(company_class='other', calendar_year=2025, total_board_strength=6,
  meetings=[date(2024,11,1),date(2024,12,15),date(2025,1,20),date(2025,3,1)])
print([(f.rule,f.satisfied,f.observed) for f in r.findings])"
```

Output: `minimum number of Board meetings in the year — True — '4 recorded'`. The company held
**two** meetings in calendar 2025. The s.173(1) floor is reported satisfied. `calendar_year` is
used only by `_halves()` in the relaxed branch; in the standard branch it is inert.

`_decide_board` also never passes `incorporation_date` or `single_director_opc` to `review()`
(`obligations.py:174`), so the s.173(1) first-meeting-within-30-days limb never runs from the
matrix at all — the code for it exists and is unreachable from the only surface.

**Cheapest mitigation:** filter `ms` to `calendar_year` inside `review()` and add a finding
naming any supplied date outside it; pass `incorporation_date` through from the profile. Two
lines and one test each. The COMPLIANT-unreachability is a design decision, not a bug — but the
matrix must then stop offering a state it cannot produce, or say on the row that "satisfied" is
unavailable for this obligation pending s.174.

### F7 — `is_listed` is collected and never read

```
grep -rn "is_listed" checker/*.py applicability.py
checker/company_profile.py:117   # the field
checker/matrix_view.py:114       # parsed from the form
checker/matrix_view.py:201       # rendered as a form control
```

Three hits. All of them are plumbing. **Nothing consumes it.** A listed public company gets an
identical four-row matrix to a private one — no s.149(4) independent directors, no s.149(1)
second proviso woman director, no s.177 audit committee, no s.178 NRC, no s.203 KMP, no SEBI LODR
at all.

This is worse than not asking. Asking "listed: yes/no" and then producing the same output is an
affirmative representation that listing was taken into account. It converts an incomplete tool
into a misleading one. The same is true of `governed_by_special_act` and `is_section_8`, which
feed only s.2(85) — a s.8 company gets no indication that s.8 changes its AGM and board regime.

**Cheapest mitigation:** remove the fields from the form until an obligation reads them, or render
a row per collected-but-unused field saying `CANNOT_DETERMINE — this system holds no obligations
conditioned on listing`. The second is more in keeping with the project's stated personality and
costs an hour.

### F16 — s.149 passes are snapshot claims dressed as period claims

`_decide_board_size` reads `p.director_count`, a single integer with no date attached, and returns
`APPLIES_SATISFIED` with basis "3 directors: at or above the minimum of 2… (numbers limbs only)".
s.149(1) is a continuing requirement. A company that fell to one director for five months and
re-appointed before the `as_of` date shows green. The row's basis never mentions `as_of`, though
the profile carries it and the render header prints it.

Compare `checker/company_profile.py`'s own `Figure`, which binds an amount to its financial year
specifically so a comparison against the wrong year is refused. The rigour applied to money was
not applied to headcount.

**Cheapest mitigation:** state the date in the basis — "3 directors **as at 2026-08-31**" — and
add "whether the minimum held throughout the period" to `open_questions`. Ten minutes.

### Where the legal layer is genuinely sound

- The five-state row vocabulary, and specifically keeping `DOES_NOT_APPLY` apart from
  `CANNOT_DETERMINE`, is correct and correctly tested (`obligations.py:_test`, "cannot tell if it
  applies never becomes does not apply").
- The relief asymmetry in `classify.py` — NOT SMALL needs one failing condition, SMALL needs every
  condition known — is exactly right and is the single best piece of legal reasoning in the repo.
- `Evidence(agm_dates=None)` vs `()` — "not told" vs "told there were none" — is right, tested,
  and survives the form (`matrix_view._dates`).
- The s.173(1) ceiling vs s.173(5) floor distinction, with `direction` on every finding, is a real
  insight about a real trap. It is undermined by F5 but not wrong.

---

## 2. EVIDENCE failure

The claim under attack: the release gate certifies something.

### What the gate actually certifies

`checker/metric_policy.py:34-38`, with the comment quoted verbatim:

```
FALSE_ACCEPT_CEILING = 10   # cascade currently 2 with the E6 gate, 13 without
F1_FLOOR = 0.40             # cascade currently 0.58; baseline is 0.00
ABSTENTION_CAP = 0.25       # cascade currently 0.00; E5 alone is 0.83
# Deliberately not aspirational — these are what the current cascade achieves
# plus a small margin, so the gate catches regression rather than blocking work.
```

The gate is **a regression detector wearing the word "release"**. That is a defensible engineering
artefact and an indefensible name, and the name is what will appear in a pitch deck.

Quantify the headroom. There are 47 negatives in the scored set. A false-accept ceiling of 10 is
therefore a permitted **21% false-accept rate on unsupported legal claims**. Now pair it with the
F1 floor: a configuration returning tp=11, fp=10, fn=9 scores precision 0.52, recall 0.55, F1 0.53,
abstention 0.00 — and **passes every axis**. That configuration serves ten unsupported statements
of Indian company law as supported, and nearly half of everything it accepts is wrong. It passes
the release gate.

`[ALREADY NAMED]` — that two of three buckets are single-label. The marginal attack is F4 below:
it is not a sampling accident, it is enforced by the fixture pipeline, so the project's implied
remedy (more human review) cannot fix it.

### F3 — the gate does not score the frozen benchmark **REPRODUCED**

`corpus/benchmark/manifest.json` attests, with SHA-256 hashes over `approved_pairs.jsonl` and over
each source span:

```
"pair_count": 69,  "label_counts": {"ENTAILED": 22, "NOT_ENTAILED": 47},
"label_basis_counts": {"CONSTRUCTED": 54, "HUMAN_JUDGED": 15}
```

What `evaluate_gate` actually scores:

```
PYTHONPATH=. python3 -c "
from checker.entail_pairs_v2 import all_pairs
from checker.grounding_policy import ENTAILED, NOT_ENTAILED
import collections
rows=[p for p in all_pairs() if p.label in (ENTAILED,NOT_ENTAILED)]
print(len(rows), collections.Counter(r.label for r in rows),
      collections.Counter(r.label_basis for r in rows))"
```

Output: **67 rows, ENTAILED 20, NOT_ENTAILED 47, CONSTRUCTED 52, HUMAN_JUDGED 15.**

Two positive pairs — `v2-p174-bind-0` and `v2-p174-bind-1`, both recorded in
`corpus/benchmark/deferred_drift.json` as "outside the authorised scope" — are present in the
frozen, hashed artifact and absent from what the gate measures.

The mechanism is the point. `entail_pairs_v2.all_pairs()` (line 427) is
`base_pairs() + approved_replacements()`, which is `rewritten_pairs()` (Python literals) +
`constructed_pairs()` (generated at import time by calling `entail_paraphrase.rebind_pairs()`) +
`approved_replacements()` (generated by `fixture_rebuild.propose()`, filtered through
`reviews.status_of()`). **The gate scores a generator. The freeze protects a file the gate never
opens.** The manifest hash will validate forever while the measured set drifts underneath it.

This is the *identical* disease the project already diagnosed and fixed one layer down.
`checker/cascade.py`'s own docstring:

> It was defined inside `metric_policy._test()`. Nothing outside that function could reach it…
> the release gate would then be scoring code that merely resembled what shipped.

The cascade was lifted out of the test. The **benchmark** was not lifted out of the generator. Same
failure, one level up, and it has already produced a live divergence.

**Detect early:** a test asserting `len(all_pairs scored) == manifest["pair_count"]` and that the
label histogram matches `manifest["label_counts"]` exactly. This test would fail today.

**Cheapest mitigation:** `evaluate_gate` reads `approved_pairs.jsonl`, verifies its SHA-256
against the manifest, and refuses to run on mismatch. The generator becomes a proposal tool, not a
measurement input. Half a day, and it is the single highest-leverage change in this document
because every accuracy number the project will ever quote flows through it.

### F4 — human review is structurally incapable of producing a negative

`checker/entail_pairs_v2.py:392-411`, `approved_replacements()`:

```python
out.append(Pair(..., label=ENTAILED, label_basis=HUMAN_JUDGED, ...))
```

The label is a **literal**. And `rewritten_pairs()` at line 345:

```python
if basis == HUMAN_JUDGED and st == REVIEW_APPROVED:
    label = ENTAILED
```

A reviewer does not record *what they judged*. A reviewer records **approval**, and approval is
compiled to ENTAILED. There is no code path anywhere in the fixture machinery by which a
human-judged pair can carry the gold label NOT_ENTAILED.

Consequences, in order of severity:

1. `paraphrase` (n=15, all 15 HUMAN_JUDGED, all ENTAILED) has zero negatives **by construction**.
   `metric_policy` correctly prints `[no negatives: cannot detect false accepts]`. What nobody has
   said is that this **cannot be fixed by reviewing more pairs**. Every additional human-judged
   pair the pipeline can produce is another positive. The bucket's blindness to false accepts is
   permanent until the fixture schema changes.
2. The review governance layer — `review_record.py`, `scoped_retraction.py`,
   `benchmark_v2_freeze.py`, `promotion_preview.py`, `resubmission.py`, described in
   `BUILD_PLAN_PRODUCT.md` as "more complete than anything user-facing" — is elaborate
   append-only machinery around a decision with **one reachable outcome**. It is provenance for a
   constant.
3. The 15 HUMAN_JUDGED labels are the entire human contribution to the benchmark. All 15 are
   ENTAILED. All 15 are from one reviewer, who is a non-lawyer. So the human-judged portion of the
   benchmark contains **zero human judgements that anything is unsupported** — which is the
   direction that matters legally.

**Detect early:** assert `len({p.label for p in all_pairs() if p.label_basis == HUMAN_JUDGED}) > 1`.
It fails today and will fail after any amount of further review.

**Cheapest mitigation:** the review decision record must carry the reviewer's *label*, not their
approval, and `Pair.label` must read it. Then the reviewer's job becomes "is this claim entailed
by this span, yes or no" rather than "approve this proposed positive". This is a one-field schema
change plus a migration of 15 records, and it is the only route to a paraphrase bucket that can
detect a false accept.

### The rest of the benchmark's limits `[ALREADY NAMED]`, with one addition

69 (67) pairs, 5 sections, 1 Act, 54 (52) constructed, 1 non-lawyer reviewer. `manifest.json`'s own
`not_a_claim_of` field says it. The addition nobody has connected:

**Two of the five sources are documented as textually corrupt by this project's own defect
register.** `docs/SOURCE_DEFECTS.md` SD-004 records `hall` for `shall` in s.174(1) and `maybe` for
`may be` in s.101(1) — and states the consequence explicitly: *"`entail_qualifier`'s
delegated-rule pattern (`as may be prescribed`) does **not** match s.101(1) for this reason — the
qualifier is present in law and invisible to that pattern."*

So E6, the **gate** of the cascade, is documented as blind to a qualifier on one of the five
sections the benchmark is built from. And the bucket that measures E6 (`dropped_qualifier`, n=9)
holds no positives, so E6 has never been observed to accept correctly. The gate's gate is measured
on a corpus where it is known blind, in a bucket that cannot score it. Nobody has drawn that line.

Could the gate pass while the system is badly wrong? **It is passing right now while the s.96 row
returns green on a live statutory default.** The gate measures span-to-claim entailment. Nothing in
it measures whether the register enumerates the right limbs. F1 is invisible to the gate by
construction, because the gate never looks at obligations.

---

## 3. ACQUISITION failure

The claim under attack: *"Refusing when a source is unacquired is a feature, not a defect."*

### The denominator

- Act sections held: **529** (`corpus/companies_act/`).
- Rule sets held: **1** — `corpus/rules/board_powers_2014.json`.
- Sections of the Act whose text contains "prescribed": **174 of 529 = 32.9%** (measured, not
  estimated: `python3 -c "import json,glob; ..."` over the corpus).

One third of the Act does not state its own operative content. It points at delegated legislation.
We hold one set of Rules out of roughly forty. The Companies Act 2013 is not self-executing and a
system holding the Act without the Rules holds the index, not the book.

### F9 — the moat is asserted over the cheap half

The strategic claim is that a public-statute corpus is a **fixed target**, so deterministic
verification over it compounds. Attack:

The fixed part — consolidated Act text — is exactly the part that is **free, public, and served by
India Code's own REST API with no key and no auth** (`CLAUDE.md`, verification status). Anyone can
have it in a weekend. It is the commoditised half.

The half that is not fixed — Rules, gazette notifications, commencement orders, MCA circulars,
form versions — is the half where verification is genuinely hard, genuinely valuable, and where
**acquisition has been blocked for twelve days on a single instrument** (S-002). The moat is being
claimed over the part that is cheap to copy, while the part that would actually constitute a moat
is the part we cannot get.

Second attack on the same claim: point-in-time reconstruction of the *whole Act* is machinery a
compliance product does not need. A compliance matrix needs the dated text of perhaps forty
recurring obligations. A lawyer could author those forty as dated versions in a fortnight and the
result would be more reliable than a reconstruction engine that `SOURCE_DEFECTS.md` reports as
PARTIAL on roughly two-thirds of amended sections. **The engine's cost is being justified by a
requirement the product does not have.**

Where the claim is sound: contract-review vendors genuinely have no reason to build commencement
provenance, and `checker/commencement.py` — the notification that appointed a date, not the
footnote that asserts it — is a real distinction most legal-tech does not draw. Keep it. Stop
selling it as the moat until something depends on it.

### F15 — fail-closed robots converts a machine task into an unbounded human queue

`checker/robots.py:214-221` is correct: a 4xx is an answer, a 5xx is not, and a 5xx denies. RFC
9309 agrees. The policy is right and I am not arguing against it.

The attack is on what it costs and what it buys **for this instrument**:

- India Code's `robots.txt` has returned HTTP 502 continuously since ~21 August. That is a broken
  web server at a government publisher of public law, not a statement of policy.
- The recorded remedy in `research/TASKS.md` S-002 is: *"Human download + `python3
  scripts/register_gsr700e.py <file>`."*
- That human download is **the same GET, to the same host, for the same public bitstream**. It
  differs in the user-agent string and in the fact that a person clicked.

So the gate does not change *what is acquired* or *whether the publisher is respected*. It changes
*who clicks*, and it adds a founder-time bottleneck of unbounded latency to a solo-founder project
with a founder-blocked ledger already four items long (H-001, H-002, H-004, S-002).

Compounding it: **nothing in the repository retries.** There is no scheduled re-attempt, no
backoff record, no "recheck robots.txt weekly" job, no alternative-source registry. A transient
5xx in one session became a permanently blocked ledger row. The policy is fail-closed; the
*process* is fail-forever.

**Cheapest mitigation:** a `scripts/retry_blocked_sources.py` that re-attempts every blocked
acquisition and appends the outcome to `corpus/sources/acquisition_*.json`, run from the existing
CI workflow on a schedule. Under an hour. It does not weaken the policy by one byte; it just stops
a 502 from being permanent.

### F11 — the refusal rate, measured **REPRODUCED**

The real question is not whether refusal is a feature. It is: what fraction of the output is
refusal, and at what fraction does a user stop returning?

Measured on three realistic profiles, with **no** event evidence supplied — which is the state of
every first session, because a practitioner opening a new matter does not have last year's AGM
date to hand:

| Profile | SATISFIED | UNDETERMINED | CANNOT_DETERMINE | DOES_NOT_APPLY |
|---|---|---|---|---|
| private, class + FY only | 0 | 3 | 1 | 0 |
| private, every status + both figures + director count | **1** | 2 | 1 | 0 |
| public, every status + director count | **1** | 2 | 0 | 1 |

**A private-company user who answers every question on the form correctly gets one decided row out
of four, and that row is the one that just counts directors.** The two rows a compliance matrix
exists for — did you hold your AGM, did you hold your board meetings — are `APPLIES_UNDETERMINED`
regardless of effort, and per F5 the board row can never be anything else.

The small-company row is `CANNOT_DETERMINE` for **every private company**, which is the only class
it can apply to. So `CA13-S2-85-SMALL` is, today, a row that produces exactly one answer for every
user who could ever need it: "blocked, S-002". It is a constant with a citation.

At what refusal rate does a user stop? I will not pretend to know, and nobody in this repo does
either — zero practitioners have seen this. But the relevant comparison is not "refusal vs wrong
answer". It is **"refusal vs the ten minutes of typing that produced it"**. The form has twelve
fields. Twelve fields in, one row of arithmetic out. That is the number to test, and it is
testable this week with the five conversations `BUILD_PLAN_PRODUCT.md` §8 already specifies.

---

## 4. PRODUCT failure

### F6 — "a full matrix" of four obligations

`checker/matrix_view.py` header, rendered to the user:

> "Obligations are generated from what the company *is*, not from documents you upload — so a
> company that has filed nothing still gets a **full matrix**."

`obligations.py:render()`: `f"  {n} of {len(rows)} rows need attention."`

`len(REGISTER) == 4`. The Act has 529 sections and roughly forty recurring corporate obligations
before you reach the Rules. **Nowhere on the surface does it say how many obligations exist, or
that four is a sample.** "N of 4 rows need attention" reads as a denominator. A practitioner
seeing "0 of 4 rows need attention" has been handed something that looks like a clean bill.

This is the project's own Stage 1 kill criterion, stated in `BUILD_PLAN_PRODUCT.md` §8: *"it looks
complete and is not, which is worse than obviously thin."* The product as written triggers its own
kill criterion at the level of the page copy, before any practitioner sees it.

It is also the cheapest fix in this entire document. One sentence: *"This register covers 4 of the
Companies Act's obligations. It is not a complete compliance check and the absence of a row is not
a finding that a duty does not exist."* Fifteen minutes. Its absence is the difference between an
honest thin tool and a misleading one.

### Is honest-and-useless still honest?

Partly, and the honesty is real: `matrix_view` states no model was consulted, states it does not
claim compliance, names the blocking task on the blocked row, and offers "not known" as the default
on every tri-state field so a defaulted zero cannot silently become a favourable answer. That last
detail — *"for a threshold shaped 'does not exceed X', zero is the strongest possible pass"* — is
better than most shipped legal software.

But there is a form of dishonesty that survives all of that: **a refusal that names the wrong
reason still misleads.** `obligations.py:335`:

```python
blocked = "S-002" if "servable" in basis or "S-002" in basis else ""
```

The blocking-task attribution is derived by **substring-sniffing the human-readable trace text for
the word "servable"**. If `ThresholdUnavailable.__init__` is ever reworded, the S-002 attribution
silently vanishes from the row and the user is told `CANNOT_DETERMINE` with no reason. And in the
common case where the user simply supplied no figures, the row still says "BLOCKED: S-002 — a
source this system has not properly acquired", pointing at an acquisition problem when the
proximate cause is a blank form field.

### What makes a practitioner abandon it in the first session

Ranked by my estimate of what actually happens:

1. **Twelve fields in, one decided row out** (F11). The effort-to-answer ratio is the first thing
   felt and the hardest to argue with.
2. **They test it on a company they know is in default and it comes back green** (F1). One
   occurrence ends the relationship permanently. Legal professionals do not give a tool a second
   chance after a false negative on a matter they know the answer to.
3. **They tick "listed: yes" and nothing changes** (F7). Anyone advising a listed company will spot
   this in under a minute.
4. **The one row that could be decided from public data — small company — refuses** (F11), and the
   figures they typed were used for nothing.
5. **No persistence.** `handle()` is a pure function with no store. Every matrix must be retyped
   from scratch, every session. The fifteen-month AGM limb inherently requires last year's data,
   and there is nowhere to put it. `BUILD_PLAN_PRODUCT.md` puts persistence in Stage 2; but the
   AGM row's whole value depends on state, so Stage 1's flagship obligation is the one Stage 1
   cannot serve.

### F12 — the moat cannot reach a user

`checker/evidence_pack.py`, docstring, verbatim:

> `checker/as_of.py` can reconstruct a section at a past date, but that reconstruction is
> UNVERIFIED against any external source… so **this pack refuses to describe itself as
> point-in-time at all.** If the caller asks for a date, the pack records the request and names it
> as something it cannot supply.

The evidence pack is, by the project's own design, the **only** channel through which provision
text reaches a model. Point-in-time reconstruction is the headline differentiator in
`COMPETITOR_FEATURE_MATRIX.md` (marked `HELD`). The pack refuses to serve it. Therefore the
differentiator is unreachable from any model-bearing surface — Stages 4, 5 and 6 — and is reachable
only from a Python prompt.

The matrix row `Point-in-time statutory reconstruction | HELD` is accurate about the code and
misleading about the product. It should read `HELD (not servable — evidence_pack refuses)`. This
is a one-cell documentation fix and it prevents the claim from being made externally on the
strength of a table.

---

## 5. STRATEGIC failure

### F10 — the code has already chosen the segment the docs forbid

`docs/PRODUCT_SCOPE.md`, locked 20 Aug: primary customer is a corporate lawyer, explicitly *"not a
product aimed primarily at Company Secretaries"*.

`docs/WORKFLOW_BACKLOG_INDIA.md` §on the do-not-build list: *"Anything targeted at a Company
Secretary before `R-011` closes."*

`checker/obligations.py:REGISTER` — the four obligations actually built: s.96 AGM, s.173 board
meetings, s.149 board composition, s.2(85) small-company classification.

**All four are Company Secretary work.** AGM convening, board-meeting calendars, board composition
and company classification are the CS's statutory function; s.203 makes it so for companies above
the threshold. `WORKFLOW_BACKLOG_INDIA.md` already says this of the workflow layer — *"Every
workflow in this backlog with strong in-repo evidence is Company Secretary work"* — but nobody has
stated the consequence: **the repository is currently in breach of its own do-not-build rule, and
has been since the register was written.** The segment conflict is no longer a planning question;
it is a shipped fact.

Then the pricing collision, which nobody has drawn:

- `CLAUDE.md`: ComplyRelax is **free to ICSI members until 31 Mar 2029**, 201 unbroken updates.
- The declared segment (lawyers) cannot get ComplyRelax free — so on the org chart there is no
  competitor.
- The **built** product serves CS work — the exact population for whom the incumbent is free for
  three more years.

So the strategy document describes a market with no free incumbent, and the code was written for
the one market where the incumbent is free. Pricing power in the built market is approximately
zero, and the wedge in `CLAUDE.md` (auditing ComplyRelax's own drifted outputs) is a wedge into
that same free-incumbent market — it presupposes the customer is already a ComplyRelax user, which
means an ICSI member, which means a CS.

That wedge is genuinely clever and I do not want to talk anyone out of it. But it cannot coexist
with `PRODUCT_SCOPE.md` in its current form. One of the two documents is wrong, and the code has
already voted.

### Interviews: four is not the problem

`research/TASKS.md` H-001 (expert review by practising corporate lawyers): **zero**. B-002
(accessible legal testers): **none**. Interviews recording workflow frequency, task duration, or
willingness to pay: **0, 0, 0**.

The usual criticism is "four interviews is too few". That is not the sharpest version. The sharpest
version is:

**Of four interviews, zero were with the declared buyer** (`WORKFLOW_BACKLOG_INDIA.md` §0.1: "Of
those, corporate lawyers: 0"). The four are property/family, general practice, one senior
generalist, and one company-side decision-maker. The segment decision of 20 Aug — the one that
demoted a segment with a public member directory, a documented enforcement corpus and a growing
vendor-empanelment channel — was made on the stated ground that *"all four real interviews are with
lawyers"*. Those four lawyers were not corporate lawyers, and the one company-side voice, asked
unprompted, named a Company Secretary.

So the pivot's evidentiary basis is four conversations with people outside the target segment, and
the only unprompted answer contradicted it. That is not a small sample. That is a sample of the
wrong population used to justify moving toward it.

The single cheapest correction in the strategic section: **one conversation with one practising
Company Secretary**, which `research/TASKS.md` H-003 already deprioritised. ICSI's member directory
is public with CoP and city filters — the repo says so. This is an afternoon.

### Solo-founder capacity

`research/TASKS.md`: 4 of 22 rows are `founder`-owned and human-only (H-001, H-002, H-004, S-002).
S-002 alone gates the small-company row, which gates the s.173(5) regime, which gates the board row
for every private company. **One human download is the critical path for half the register.** It has
been open for twelve days.

Meanwhile `checker/` holds 78 self-testing modules and 25,902 lines. The ratio of engineering
throughput to founder-task throughput is the actual risk: the code is outrunning the evidence, the
acquisitions and the users by a very large factor, and every additional module widens the gap
between what has been built and what has been validated. `B-001` — the one measurement that would
falsify the entire "deterministic core is the moat" thesis — is marked **CRITICAL PATH** with
evidence "none".

---

## 6. TECHNICAL failure

### F2 — client-confidential data in a GET query string

`checker/matrix_view.py:191`: `<form method="get" action="/matrix">`.

The twelve fields include paid-up share capital, turnover, incorporation date, director count,
listing status, AGM dates, and board-meeting dates. That is, for a law firm, a client company's
financial position and its compliance defaults. It all travels in the URL.

`vercel.json` then does:

```json
{ "source": "/(.*)", "destination": "/api/index?__p=%2F$1" }
```

The deployment target is Vercel. A GET URL is written to Vercel's request logs, retained by a US
vendor, and is visible in browser history, in the `Referer` header of any outbound link, in any
corporate proxy, and in any shared or bookmarked link. `api/index.py` confirms the whole
application is behind that rewrite.

There is **no authentication, no session, no transport of anything by POST, no privacy notice, and
no data-handling statement anywhere in the repository.** `grep` for auth in `matrix_view.py`
returns nothing; the module docstring is proud that `handle()` is a pure function with no I/O and
no globals — and it is exactly that purity that forces every fact into the URL.

For the declared buyer this is disqualifying. An Indian advocate handling client company data has
confidentiality obligations under the Bar Council of India Rules; a firm's IT policy will not
permit client financials in third-party access logs. The very first enterprise conversation ends
here. And it is not a legal-nicety objection — it is the objection a solo practitioner will also
raise, because they can see the data in their own address bar.

**Detect early:** show the URL to any practitioner. Zero conversations required; it is visible in
one screenshot.

**Cheapest mitigation:** `method="post"` with the results rendered from the request body, no
persistence. `handle()` stays pure — it takes a params dict either way; only `api/index.py` and one
form attribute change. Half a day including a CSRF token. Add a one-paragraph statement on the
page saying what is and is not stored. Until then, do not put this URL in front of anyone with a
real client.

### F8 — the budget guard cannot enforce on the target it was written for

`backend/budget.py` docstring, verbatim:

> **Persistence.** The spec's tracker holds counters on `self`. On serverless every invocation may
> be a fresh process, so an in-memory tracker resets to zero on each request and enforces nothing.
> This one persists to a JSON file…

The diagnosis is exactly right and the remedy reintroduces the bug. `FileStore` defaults to
`corpus/.budget.json` (line 89) — inside the deployment bundle. On Vercel:

- the function filesystem is **read-only** except `/tmp`, so `write()` (line 101, `mkdir` +
  `write_text` + `replace`) raises `OSError`;
- `/tmp` is **per-instance and ephemeral**, so even if the path were moved there, N concurrent
  instances each read `{}`, each allow spending up to the full cap, and each write their own
  counter. The cap becomes per-instance, not global;
- `.gitignore:11` excludes `corpus/.budget.json`, so the file is never in the bundle and
  `read()` always returns `{}` → `spent_today = 0` → **every call is allowed**.

Then the failure is swallowed. `checker/model_adapter.py:322-330`:

```python
try:
    budget.record_call(spent)
except (ValueError, OSError) as e:
    _LEDGER_WRITE_FAILED.append(str(e))
```

```
grep -n "_LEDGER_WRITE_FAILED" checker/model_adapter.py
114:_LEDGER_WRITE_FAILED: list[str] = []
330:            _LEDGER_WRITE_FAILED.append(str(e))
```

**Written once, read never.** It is not in `ModelResult.warnings`, not logged, not surfaced to any
caller. It dies with the process.

Net effect at Stage 4: a ₹3,500/month cap that reads zero, allows every call, fails to record every
call, and reports the failure to a list that no code reads. The failure direction is **unbounded
spend on a solo founder's card**, and it is invisible. `model_adapter.py`'s docstring says a real
model with no budget tracker is refused because *"spending against an unknown balance is exactly
what backend/budget.py refuses to do"* — but a tracker whose store always returns `{}` is
functionally a tracker against an unknown balance that reports "₹0.00 spent".

The comment on the swallow is defensible in isolation ("losing the answer we already paid for makes
it worse") and indefensible as written, because "surface it" is not what the code does.

**Detect early:** a test that constructs a `FileStore` on a read-only directory and asserts the
tracker refuses rather than allows. It fails today.

**Cheapest mitigation, in order:** (1) put `_LEDGER_WRITE_FAILED` into `ModelResult.warnings` — one
line, and it converts an invisible failure into a visible one; (2) make `BudgetTracker` refuse when
its store cannot be written, i.e. treat an unwritable ledger as an exhausted one, matching the
module's own "corrupt ledger must not authorise spending" rule at line 96 which already gets this
right for the read path; (3) before Stage 4 ships, move the store to Supabase — the `Store`
Protocol already exists for exactly this.

### F13 — the s.52 copyright guard is a three-string blocklist

`matrix_view._test()`:

```python
for phrase in ("Every company shall hold", "paid-up share capital of which",
               "shall be the quorum"):
```

s.52(1)(q)(ii) of the Copyright Act permits reproduction of an Act **together with commentary**.
The project's stated posture is that the page must never render statutory text as its own content
(module docstring), and the test asserting it checks for **three hardcoded literals**. The moment
any `Obligation.note`, `Row.basis`, or a future evidence card carries a longer quotation, the guard
does not notice. It cannot notice: it is a denylist of three strings against an Act of 529
sections.

The docstrings of `classify.py` and `prescribed_thresholds.py` already quote s.2(85) at length —
correctly, since they are not served — but that is exactly the material that gets copy-pasted into
a `basis` string by a future edit.

**Cheapest mitigation:** invert it. Assert that no contiguous run of ≥ N words in the rendered page
appears verbatim in `corpus/companies_act/*.json`. That is a real invariant, it is cheap (the
corpus is 519k characters and already loaded), and it survives edits. Half a day.

### F14 — a packaging failure is indistinguishable from a legal refusal

`checker/prescribed_thresholds.py:_prescribed_state()`:

```python
try:
    from scripts.register_gsr700e import registration, is_attested
except ImportError:
    return UNRESOLVED, "the registration module could not be imported"
```

Library code importing from `scripts/`. If `scripts/` is not in the serverless bundle — and there
is no reason it would be — production returns `UNRESOLVED` and the matrix renders "BLOCKED: S-002 —
a source this system has not properly acquired". Which is what it renders when the source genuinely
is unacquired.

So: after a human finally downloads G.S.R. 700(E) and registers it, **production keeps refusing**,
and the message will say the source was not acquired. The team will look for an acquisition problem
that has already been solved. The two states must be distinguishable.

**Cheapest mitigation:** distinct notes for `ImportError` ("registration machinery unavailable in
this deployment") vs no registration on record, and a startup assertion that the module imports.
An hour.

### Scale, OCR, multi-state, listed `[ALREADY NAMED, partly]`

- **OCR:** assumption 12 in `BUILD_PLAN_PRODUCT.md` §9 already says "UNVERIFIED and probably false".
  The marginal attack: Stage 1 needs no documents, so the risk is deferred — but so is every
  document-side validation, and Stage 4's kill criterion depends on OCR error rates nobody has
  measured. The project has arranged its build order so the largest untested assumption is tested
  last. Twenty documents in the format they actually arrive in, per `WORKFLOW_BACKLOG_INDIA.md`,
  settles it in a week and should be moved ahead of Stage 2.
- **Multi-state:** the Companies Act is central, so state variation is genuinely a non-issue here.
  Sound. Move on.
- **Listed:** not a scale problem, a correctness problem. See F7.
- **Scale:** `handle()` is pure and stateless; there is nothing to scale and nothing to lose. This
  is genuinely fine and is the best consequence of the Stage 1 design.

### Where the technical layer is genuinely sound

- CI (`.github/workflows/tests.yml`) runs the identical script the pre-commit hook runs, with an
  explicit comment about why two definitions of "green" must not exist. Correct.
- `robots.py`'s 4xx-vs-5xx distinction and its refusal to use `ssl._create_unverified_context()`
  are both right, and the reasoning given for each is right.
- `Money` in whole rupees with `lakh()`/`crore()` constructors, and `Figure` binding an amount to a
  financial year, are the correct shapes and prevent a whole class of silent error.
- `model_adapter`'s four pre-call refusals and its fail-closed parse are a good contract. It is
  untested against a real model, which the project says itself.

---

## 7. Failure modes nobody in this project has named

This is the section that matters. Six of these are above; they are listed here by name so the
section is complete, and the three that are only here are the ones I would act on first.

| | Finding | Where |
|---|---|---|
| N1 | **The gate does not score the frozen benchmark.** The freeze protects a file; the gate scores a generator. Already diverged: 67 vs 69. | F3 |
| N2 | **Human review can only produce ENTAILED.** The single-label bucket is enforced by `approved_replacements()`, not sampled. More review cannot fix it; the whole review-governance stack has one reachable outcome. | F4 |
| N3 | **Client-confidential financials in a GET URL to a third-party host.** No auth, no POST, no privacy notice. Visible in one screenshot. | F2 |
| N4 | **The budget guard reintroduces the exact bug its docstring diagnoses,** and its failure path writes to a list nobody reads. | F8 |
| N5 | **`is_listed` is collected and never read** — the form makes a representation the engine does not honour. | F7 |
| N6 | **The s.173 row cannot reach "satisfied", and `calendar_year` does not filter meetings.** A dead branch is protected by a disjunctive test. | F5 |
| N7 | **SD-004 × benchmark composition × the E6 bucket.** E6 is documented blind to a qualifier on 1 of 5 benchmark sources, and the bucket that scores E6 holds no positives. Three known facts; the product of them was never taken. | §2 |
| N8 | **The moat cannot reach a user:** `evidence_pack` refuses to serve point-in-time, and it is the only channel to a model. `COMPETITOR_FEATURE_MATRIX.md` marks it `HELD`. | F12 |
| N9 | **The code has already chosen CS,** putting the repo in breach of its own do-not-build rule, in the one market where the incumbent is free until 2029. | F10 |
| N10 | **Blocked-task attribution is derived by substring-sniffing trace prose** for the word `"servable"`. A reworded exception message silently removes the only explanation the user gets. | §4 |
| N11 | **The register has no denominator.** "N of 4 rows need attention" reads as a complete matrix of the Act. The page says "full matrix". | F6 |
| N12 | **Nothing retries a blocked acquisition.** Fail-closed policy, fail-forever process. | F15 |
| N13 | **The self-test suite passes on dead branches.** F5's `check(state in (SATISFIED, UNDETERMINED))` is green on an unreachable disjunct; the s.52 guard is green on three literals. 78 green suites is a weaker signal than it reads as. | below |
| N14 | **Self-documented weakness is discharging the cost of fixing it.** Every finding in `BUILD_PLAN_PRODUCT.md` §1.5 has been true and written down since 1 September, and none has moved. The docs are becoming a place where problems go to be acknowledged. | below |

### N13 — the suite is green on branches that cannot execute

Two demonstrated instances, and a class:

1. `obligations._test`: `check(b.state in (APPLIES_SATISFIED, APPLIES_UNDETERMINED), "four spaced
   meetings resolve or abstain, never fail")`. `APPLIES_SATISFIED` is unreachable (F5). The
   assertion passes forever on the second disjunct and reads as though it tests the first.
2. `matrix_view._test`: the s.52 guard is a three-literal denylist (F13). Green regardless of what
   is added to the page.

The class: **disjunctive and negative assertions in a self-test suite are the places where dead
code hides.** With 78 modules each carrying its own `_test()` and its own `check()` helper, there
is no coverage measurement anywhere in the repo — `scripts/run_tests.sh` reports pass/fail per
suite, not lines executed. So the project's headline quality signal ("all 78 suites green") is
consistent with a substantial fraction of the code being unreachable.

**Detect early:** run the suite under `coverage.py` once. It is a stdlib-adjacent single dependency
and can be dev-only. Any branch at 0% in a module whose test claims to cover it is an N13.

**Cheapest mitigation:** one coverage run, and a rule that a `check()` whose condition is a
disjunction over states must assert which disjunct held.

### N14 — the documentation is absorbing the work

`docs/` holds 46 files and roughly 500KB of prose. `BUILD_PLAN_PRODUCT.md` alone is 52KB;
`WORKFLOW_BACKLOG_INDIA.md` 62KB; `FEATURE_PLAN_INDIA.md` 52KB; `AGENT_ARCHITECTURE_PLAN.md` 48KB.
All four were written in the last week of August. All four are good.

Set against them: `research/TASKS.md` has **1 completed row since 22 August** and four rows blocked
on the founder, one of which (S-002) is a single file download that gates half the register.

The failure mode is not "too much documentation". It is specific and it is the reason this analysis
exists: **a project that writes down its weaknesses in high-quality prose gets most of the
psychological reward of having addressed them.** `BUILD_PLAN_PRODUCT.md` §1.5 is a better statement
of this project's problems than most external reviews would produce. It was written on 1 September.
The s.96 row still returns green on a live default; the gate still scores 67 rows against a
manifest of 69; `is_listed` is still unread. None of those is in any document — which is the test
of whether documentation is doing work or replacing it.

**Cheapest mitigation:** a hard rule that a finding recorded in a docs file must, in the same
commit, become a row in `research/TASKS.md` with an owner. Nothing else. The ledger already exists
and is already described as the single source of truth; it is simply not fed by the documents.

---

## 8. The five things I would do this week

In order. All five are under a day each except the first, which is under two.

1. **Make `evaluate_gate` read `approved_pairs.jsonl` and verify its hash against the manifest**
   (F3/N1). Every accuracy claim this project will ever make flows through this function, and it is
   currently measuring a generator that has already drifted.
2. **Change the form to POST and add a sentence about what is stored** (F2/N3). The current design
   cannot be shown to a practitioner with a real client, and that is the only test that matters.
3. **Add a `limbs` field to `Obligation` and forbid `APPLIES_SATISFIED` while any limb is
   unimplemented** (F1). This turns the worst output in the product — a green badge on a live
   statutory default — into the product's own stated thesis.
4. **Add one sentence to the matrix page giving the denominator** (F6/N11), and remove or neutralise
   `is_listed` (F7/N5). Fifteen minutes and one hour respectively, and together they are the
   difference between honestly thin and misleadingly complete.
5. **Talk to one practising Company Secretary** (F10/N9, `research/TASKS.md` H-003). The code has
   already chosen the segment. Find out whether it chose right before writing another 25,000 lines
   for a buyer nobody in this project has met.

---

## 9. The one-paragraph version

The verification machinery is real and unusual; the legal register on top of it is four
obligations, of which one can never return a pass, one returns green on a live statutory default
and red on a company with no duty yet, one is permanently blocked for every company it can apply
to, and one decides two limbs of four while a field the form collects is read by nothing. The
release gate is a regression detector whose thresholds were set to current performance, which
permits a 21% false-accept rate on unsupported legal claims, and which does not score the
benchmark the manifest attests to — a divergence that already exists, caused by exactly the
disease the project diagnosed and fixed one layer down. The benchmark's human-judged portion
contains zero human judgements that anything is unsupported, and cannot contain one, because the
fixture pipeline hardcodes the label. The product ships client financials in a URL to a third-party
host with no authentication. The moat is asserted over the free, public, commoditised half of the
corpus while the half that would constitute a moat is blocked on a single file nobody has
downloaded in twelve days, with no retry. And the four obligations that were built are Company
Secretary work, on the repository's own do-not-build list, aimed at the one market where the
incumbent is free until 2029 — a contradiction that is no longer a planning question, because the
code has already voted.
