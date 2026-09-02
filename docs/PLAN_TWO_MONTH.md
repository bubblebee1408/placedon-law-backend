# Two-month technical and feature plan — September and October 2026

    written    : 2026-09-02
    covers     : Wed 2 Sep 2026 -- Sat 31 Oct 2026 (8 weeks + a 4-day close-out)
    method     : draft -> adversarial critique -> synthesis, per
                 `.claude/plans/loop-two-month-plan.md`
    supersedes : nothing. This is the schedule the other five plans do not have.

---

## 0. What this document is, and what it deliberately is not

Five planning documents already exist and are still correct:

| Document | What it settles | What it does not settle |
|---|---|---|
| `docs/BUILD_PLAN_PRODUCT.md` | six surfaces, stage gating, cost per stage, kill criteria per stage | *when* |
| `docs/FEATURE_PLAN_INDIA.md` | F1–F14, the matrix column spec, s.52(1)(q)(ii) posture | *when*, and which obligation next |
| `docs/WORKFLOW_BACKLOG_INDIA.md` | W1–W14 ranked, and that our user evidence is four interviews with zero corporate lawyers | *when* |
| `docs/AGENT_ARCHITECTURE_PLAN.md` | agent decomposition, model routing, per-call cost, why no vector DB | *when* the stub dies |
| `docs/ACQUISITION_POLICY.md` | how a source may be fetched and what must be recorded | which source next |

**This document adds exactly one thing: dates, and what is allowed to be said on each of them.**
It does not restate the six surfaces, the fourteen features, the fourteen workflows, or the agent
decomposition. Where it needs one of those it cites the section and moves on.

The runbook's stop condition is the contract this document is written against:

1. dated milestones tied to code that exists — §3
2. every market claim carrying VERIFIED / UNVERIFIED / ASSUMED — §9
3. a named risk register with a mitigation per risk — §7
4. an adversarial critique whose surviving objections are answered in the text — §11
5. kill criteria: what evidence would say the plan is wrong — §8

---

## 1. Ground truth, measured on 2 Sep 2026

Everything in this section was read out of the repository today, not recalled. The command that
produces each figure is given so the number can be re-derived rather than believed.

### 1.1 What runs

`bash scripts/run_tests.sh` at the last commit (`a392520`) — **all suites green**, 74
self-testing modules plus 17 script harnesses. This is the baseline every week below must preserve.

**In-flight, uncommitted, as this is written:** the working tree carries changes to
`checker/obligations.py`, `checker/matrix_view.py`, `checker/s173_slice.py` and
`scripts/serve_matrix.py` — 4 failing checks in `obligations.py` (48/52) and 1 in `matrix_view.py`
(34/35). Two things are being added: `Obligation.limbs_not_decided` (§1.2) and a POST route so
company facts arrive in a request body rather than a URL (§1.3). Week 1 assumes both land green.
If they do not, finishing them **is** week 1 and everything shifts a week — recorded here rather
than discovered later.

### 1.2 The obligation register

`checker/obligations.py`, 625 lines. **Four obligations**:

| id | provision | decided by | state today |
|---|---|---|---|
| `CA13-S96-AGM` | s.96(1) | `_decide_agm` | decides **one limb only** — the fifteen-month gap. Says so in the row basis: `"(this limb only)"`. |
| `CA13-S173-BOARD` | s.173(1) | `_decide_board` → `checker/s173_slice.review` | live; blocked for private companies because the s.173(5) regime turns on small-company status |
| `CA13-S149-BOARD-SIZE` | s.149(1) | `_decide_board_size` | numbers limbs only; the woman-director prescription is surfaced and **never decided** |
| `CA13-S2-85-SMALL` | s.2(85) | `checker/classify.small_company` | refuses — `blocked_by="S-002"` |

Five row states (`APPLIES_SATISFIED`, `APPLIES_NOT_SATISFIED`, `APPLIES_UNDETERMINED`,
`DOES_NOT_APPLY`, `CANNOT_DETERMINE`), `NEEDS_ATTENTION` covering the last three of those that
require a reader. The `Evidence` dataclass carries six fields and its docstring holds the rule that
matters most: *absent is not zero*.

**`Obligation.limbs_not_decided` (in flight, and it changes §4's arithmetic).** A duty carrying any
undecided limb can no longer render `APPLIES_SATISFIED` at all — `build()` converts a would-be pass
into `APPLIES_UNDETERMINED` with the undecided limbs as `missing_facts`, on the reasoning that a
partial pass under a green badge reads as a full pass. Today `CA13-S96-AGM` names three undecided
limbs and `CA13-S149-BOARD-SIZE` names one, which means **two of four obligations are currently
incapable of ever showing a pass.** That is the correct behaviour and it is also the strongest
possible argument for week 1: completing s.96's limbs does not merely add precision, it empties
that tuple and turns a row that can only ever say "undetermined" into one that can say "met".

### 1.3 The only Companies Act HTTP surface

`checker/matrix_view.handle()` — a pure function, standard library only, no model, no network.
`scripts/serve_matrix.py` binds `127.0.0.1` deliberately and sets `Cache-Control: no-store`, a
`default-src 'none'` CSP, and logs the path but never the query string (the query string carries a
client's financials). In flight: a POST route with a 64 KB body cap, so facts stop travelling in
the URL at all — a strictly better answer than not logging them. **This is the whole product
surface today.** There is no login, no
persistence, no multi-company view.

### 1.4 The model layer

`checker/model_adapter.py`, 664 lines, **stubbed**. Four pre-call refusals, all tested:

1. a non-`MODEL` pack raises `AdapterError`
2. a pack with no admissible evidence returns `INSUFFICIENT_EVIDENCE` with **no model call**
3. a real callable with no budget tracker and no `NO_SPEND` returns `BUDGET_EXHAUSTED`
4. a claim citing an id outside the pack is **rejected, never repaired**

Plus the downgrades: `DECISION_DOWNGRADED`, `DECISION_WITHOUT_CLAIMS`, `DUPLICATE_CLAIM_ID`
(all copies rejected, so emission order never decides a legal conclusion), and a bare `except
Exception` that converts any parse crash into an abstention.

**Three modules named in `docs/AGENT_ARCHITECTURE_PLAN.md` §8 Stage 0/2 do not exist:**
`checker/step_log.py`, `checker/orchestrator.py`, `checker/extract_adapter.py`.
`checker/cascade.py` **does** exist (206 lines, E6→E5→E4→E3) — that Stage 0 item is done.

### 1.5 The budget

`backend/budget.py`: `MONTHLY_CAP_INR = 3_500.0`, `DAILY_CAP_INR = 116.67` (derived, not
asserted), `USD_INR = 95.23` dated 2026-08-06 and therefore **four weeks stale**. List pricing is
used deliberately on the rule that *a budget guard must only ever be wrong in the expensive
direction*.

### 1.6 The rules position — this is worse than "we hold one rule set"

    PYTHONPATH=. python3 -c "import json; d=json.load(open('corpus/rules/board_powers_2014.json')); \
      print(d['short_title'], d['gazette'], d['gazette_date'], d['status'], d['production_usable'])"

We hold **one** rule instrument: The Companies (Meetings of Board and its Powers) Rules, 2014,
G.S.R. 240(E) of 31-03-2014, 15 rules, 22 pages, sha256 `b8b2e01b…`. And:

- its admission state is `HUMAN_REVIEW_PENDING`, `production_usable: false`, with one open review
  item `ri-board_rules_2014-001` whose reason is *"nobody has read this against the gazette"*;
- `checker/admission.servable(rec, MODE_MODEL)` therefore returns **False** for all 15 rules;
- every rule carries an extraction warning. Rule 6 reads *"every listed companies an d the
  following classes"*, *"one h undred crore"*, *"ou tstanding"*. Across the 15 rules the warnings
  count **~1,300 split words**;
- Rule 15 (related-party, 13,401 chars) carries a second warning: *"body runs to end-of-document
  and contains Annexure/Form matter — the operative text ends earlier; a reviewer must set the
  boundary"*;
- **there is no amendment chain.** The JSON has no amendments key. What we hold is the principal
  rules **as made on 31 March 2014**. G.S.R. 240(E) has been amended repeatedly since.

So the honest statement is not "we hold one rule set against 529 Act sections". It is:

> **We hold zero production-usable rules, and the one instrument we have is a twelve-year-old
> as-made text with a thousand-odd broken words in it.**

The second rule-shaped artefact, `corpus/provisions/companies_accounts_rules_2014.json`, carries
its own `PROVENANCE_WARNING`: it was read off a legal-news site, *"a quotation of a quotation"*,
covering essentially one clause (Rule 8(5)(x)). It is not an acquisition and must not be counted
as one.

### 1.7 How much of the Act this bounds

    PYTHONPATH=. python3 -c "import json,glob,re; n=p=0
    for f in glob.glob('corpus/companies_act/*.json'):
        if '_index' in f or '_manifest' in f: continue
        t=re.sub(r'<[^>]+>',' ',json.load(open(f)).get('content') or ''); n+=1
        p+= bool(re.search('prescribed', t, re.I))
    print(n, p, round(100*p/n,1))"

    527 174 33.0

**174 of 527 section records (33.0%) contain the word "prescribed".** MEASURED, and crude in both
directions: it over-counts (a section that merely prescribes a *form* is still fully decidable on
applicability) and under-counts (delegation reached by cross-reference is invisible to a word
match). Treat it as an order-of-magnitude bound, not a coverage figure, and never quote it
externally. The defensible sentence is: *roughly a third of the Act's sections point at delegated
legislation, and we hold one instrument of it, unreviewed.*

---

## 2. The one thing about this particular eight weeks

s.96(1) second proviso, quoted verbatim from `corpus/companies_act/` via
`checker.section_index.section_by_number("96")`:

> *"Provided that in case of the first annual general meeting, it shall be held within a period of
> nine months from the date of closing of the first financial year of the company and in any other
> case, within a period of six months, from the date of closing of the financial year"*

s.137(1): *"shall be filed with the Registrar within thirty days of the date of annual general
meeting"*. s.92(4): *"within sixty days from the date on which the annual general meeting is held
or where no annual general meeting is held in any year within sixty days from the date on which
the annual general meeting should have been held"*.

For a company whose financial year closed 31 March 2026: AGM due **30 September 2026** (week 4 of
this plan), AOC-4 due **30 October 2026** (week 8), MGT-7 due 29 November. The entire AGM→filing
chain falls inside this document's window.

**What this justifies and what it does not.** It justifies the obligation ordering in §4 — s.96,
then s.137, then s.92(4) — because those three rows are pure date arithmetic off statutory text we
hold verbatim, they need no rule we do not have, and they chain off a single fact (the AGM date).
It does **not** justify a claim that practitioners feel this pain now. `docs/WORKFLOW_BACKLOG_INDIA.md`
§0.1 records **zero interviews with a recorded workflow frequency**, and the 31-March financial
year is the s.2(41) default rather than a universal fact. So:

- *the deadlines* — **VERIFIED** against our own corpus.
- *that 31 March is this company's year end* — **ASSUMED**, and the code must never assume it:
  `CompanyProfile` deliberately has no derived financial year, and `Evidence.financial_year_end`
  stays `None` until told.
- *that this makes September the right month to talk to practitioners* — **ASSUMED**, useful for
  outreach framing, load-bearing for nothing in the build.

---

## 3. The eight weeks

Each week states: the dated deliverable, the gate that says it shipped, the **minimum ship** if
the week goes badly (solo-founder slack, see RISK-06), and an explicit **does not yet claim**.

No week in these eight weeks depends on a model for a legal conclusion. The only model call
introduced is the extractor, in week 5, in shadow.

---

### Week 1 — Wed 2 Sep → Tue 8 Sep
#### Ship: the AGM chain, complete and Act-only

**Code.**

- `checker/obligations.py::_decide_agm` currently decides one limb. Extend it to the two other
  Act-only limbs of s.96(1) quoted in §2: first AGM within nine months of the first financial
  year's close; any other case within six months of the financial year's close. The third proviso
  (Registrar's extension, up to three months, not available for a first AGM) is an **input fact**
  the user supplies — never inferred, never assumed granted.
  **Then remove the corresponding entries from `CA13-S96-AGM.limbs_not_decided`.** Per §1.2 that
  tuple currently makes the row structurally incapable of showing a pass, so this is the week's real
  deliverable: the first obligation in the register that can say "met" about a whole provision
  rather than about one limb of it. The extension entry stays in the tuple until the row can accept
  a supplied extension, and emptying the tuple is only legitimate when every named limb is genuinely
  decided — shortening it to make a green row appear would be the precise failure the mechanic was
  added to prevent.
- Two new register rows, both pure arithmetic off the AGM date already collected:
  - `CA13-S137-AOC4` — s.137(1), thirty days from the AGM. The fourth proviso's OPC limb (*"one
    hundred eighty days from the closure of the financial year"*) is a separate branch keyed on
    `CompanyProfile.company_class == "opc"`, mirroring how `_agm_applies` already handles the OPC
    exclusion.
  - `CA13-S92-RETURN` — s.92(4), sixty days from the AGM **or from the date it should have been
    held**. That second limb is the one worth building: it makes the row decidable for a company
    that held no AGM at all, which is precisely the no-document row
    `docs/FEATURE_PLAN_INDIA.md` §0 says is the whole point of the inversion.
- `Evidence` gains `is_first_agm: bool | None` and `registrar_extension_days: int | None`;
  `checker/matrix_view.parse_evidence` carries both under the existing "unknown survives the form"
  rule (`_tri` / `UNKNOWN` → `None`). No field may default.
- **The form selection is refused, not guessed.** MGT-7 versus MGT-7A is prescribed by the
  Companies (Management and Administration) Rules 2014, which we do not hold. The row gives the
  *deadline* and names the missing instrument for the *form*. Deadline and form are different
  questions and the register must answer one while refusing the other.

**Founder track, starting today, not in week 6.** `docs/validation_kit.html` exists (commit
`a392520`). Send it to five named practitioners. H-001 is recorded in `research/TASKS.md` as having
**zero** evidence and as gating every claim; it has the longest lead time of anything in this plan
and it is a human task, so it starts in week 1.

**Gate:** `scripts/run_tests.sh` green (including the in-flight work of §1.1), plus new
assertions — an AGM date with no financial-year end produces `APPLIES_UNDETERMINED` on
`CA13-S137-AOC4` and **not** a pass; a company told it held no AGM produces
`APPLIES_NOT_SATISFIED` on `CA13-S92-RETURN` via the "should have been held" limb; an OPC takes the
180-day branch; a fully-evidenced s.96 row reaches `APPLIES_SATISFIED`, which no s.96 row can do
today; and the two new obligations each declare their own `limbs_not_decided` (s.137's adjourned-AGM
provisos; s.92's form and certification limbs) rather than leaving the tuple empty by default.

**Does not yet claim:** that it knows any company's financial year end (s.2(41) makes it
underivable from a date); that an extension was granted; that a filing actually happened — the row
says a duty attaches and by when, never that it was discharged; anything about accuracy.

**Minimum ship:** s.137 alone. It is one date subtraction against text we hold verbatim.

---

### Week 2 — Wed 9 Sep → Tue 15 Sep
#### Ship: the one rule set we hold stops being a lie of omission

**Code and review.**

- Transcription verification of Rules **6 and 7 only** against pages 15–16 of
  `corpus/sources/companies_meetings_board_powers_rules_2014.pdf` (sha256 `b8b2e01b…`). Rule 6 is
  747 chars with 33 split words; Rule 7 is 1,568 chars with 66. This is transcription checking, not
  legal judgement — a human comparing our extraction to the page — and is therefore a task the
  founder can complete without a lawyer. **That distinction is deliberate and load-bearing:**
  fixing `"ou tstanding"` needs eyes, deciding whether Rule 6 states the law needs H-001.
- Route through `checker/review_queue.create_items()` → `assign()` → `decide()` →
  `apply_to_admission()`, then `checker/admission.transition()`.
- **Destination state: `DEFECT_FLAGGED_PRODUCTION_LIMITED`, not `PRODUCTION_USABLE`**, with
  `restriction_codes=("AS_MADE_2014_AMENDMENT_CHAIN_UNACQUIRED",)`. This state already exists in
  `checker/admission.py`, is already in `SERVABLE_STATES`, and already forces the pack builder to
  honour its restriction codes. It is the exactly-right shape for *"this is real text, correctly
  transcribed, and it is the 2014 as-made version"*.
- The other 13 rules stay `HUMAN_REVIEW_PENDING` with their warnings intact. Rule 15 additionally
  gets its boundary problem written into a review item rather than silently parsed.
- `checker/matrix_view` gains a **"what we cannot answer, and why"** panel driven off
  `Row.blocked_by` and `admission.blocked_reason()`. Today a blocked row prints `BLOCKED: S-002` in
  the text render and nothing structured on the page.

**Gate:** `checker/admission.servable()` returns True for R6/R7 in `MODE_MODEL` **with** a
non-empty restriction list, and False for the other 13; a test asserts that no rule reaches
`PRODUCTION_USABLE` while the amendment chain is unacquired.

**Does not yet claim:** that these rules are current law. The restriction code is a statement that
they are not.

**Minimum ship:** the blocked-rows panel. It is honest output about a state that already exists.

---

### Week 3 — Wed 16 Sep → Tue 22 Sep
#### Ship: s.177 — the first obligations that touch a Rule, and the two-limb pattern

`CA13-S177-AUDIT-CMTE`. s.177(1), verbatim from our corpus: *"The Board of Directors of [every
listed public company] and such other class or classes of companies, as may be prescribed, shall
constitute an Audit Committee."*

This obligation earns its place because it splits cleanly the way `CA13-S149-BOARD-SIZE` already
does — one limb decidable from the Act alone, one limb delegated:

- **listed public company → `APPLIES` from the Act, no rule needed.** This is a row we can serve
  at full confidence today.
- **other classes → Rule 6 of G.S.R. 240(E)**, promoted in week 2 under restriction. Rule 6's
  three tests are paid-up capital ≥ ₹10 crore, turnover ≥ ₹100 crore, or aggregate outstanding
  loans/borrowings/debentures/deposits > ₹50 crore, and its Explanation fixes the measurement date
  as *"the date of last audited Financial Statements"*.
- **composition — s.177(2), three directors with independent directors in a majority — is NOT
  decided.** "Independent director" is prescribed by the Companies (Appointment and Qualification
  of Directors) Rules 2014, which we do not hold. Surfaced, never decided, exactly as the
  woman-director limb is in `_decide_board_size`.

`CA13-S177-9-VIGIL` — Rule 7, same instrument, same restriction: listed companies, deposit-accepting
companies, and companies borrowing over ₹50 crore from banks and public financial institutions.

**A schema problem this exposes, and the honest fix.** `checker/company_profile.Figure` binds an
amount to a *financial year* because s.2(85)(ii) asks for the immediately preceding financial year.
Rule 6's Explanation asks for a different reference point — the date of the last audited financial
statements. A `Figure` carrying a financial year cannot answer a question asked about a date.
`company_profile.py`'s own rule is that a comparison against the wrong year is *refused rather than
computed*; the same must hold here. So week 3 either adds a date-bound figure type or the Rule 6
limb returns `CANNOT_DETERMINE` naming the mismatch. **It does not quietly reuse the financial-year
figure.**

New `CompanyProfile` fields: `is_listed: bool | None`, and the Rule 6 aggregate. Both default to
`None`.

**Gate:** a listed public company gets `APPLIES_*` on s.177 with no rule dependency in its basis; an
unlisted public company with unknown figures gets `APPLIES_UNDETERMINED` naming the three tests; the
row basis carries the `AS_MADE_2014` restriction wherever Rule 6 was used.

**Does not yet claim:** committee composition; that Rule 6 as we hold it is the current
prescription.

**Minimum ship:** the listed-public limb only. It needs no rule at all.

---

### Week 4 — Wed 23 Sep → Tue 29 Sep
#### Ship: the extractor's harness, with no model behind it and ₹0 spent

This is the week that makes week 5 safe. Nothing here calls a model.

- **`checker/step_log.py`** — append-only JSONL, one record per step, the schema in
  `docs/AGENT_ARCHITECTURE_PLAN.md` §6.2(c): `step_id, matter_id, task_type, prompt_version,
  model_name, pack_keys[], pack_sha256, input_tokens, output_tokens, cost_inr, decision, claims[],
  rejected_claims[], started_at, finished_at`. Same discipline as `checker/review_record.append()`:
  a wrong record is superseded by a later one naming it, never edited. This is the artefact that
  gives audit, measured per-matter cost, replay and the cache key from one file, and **it does not
  exist**, so per-matter cost has never been measured — only estimated.
- **`checker/extract_adapter.py`** — the contract in `AGENT_ARCHITECTURE_PLAN` §2.4, built and
  tested against stubs:
  1. per slot: a value, the **verbatim substring** it came from, and a character offset;
  2. the substring must occur **at that offset** in `document_text`, exact after whitespace
     normalisation only — no fuzzy matching, ever;
  3. the value must be derivable from the span by a deterministic parser (`checker/matter._parse_date`
     already exists for dates);
  4. any failure → slot is `UNKNOWN`. Never repaired, never guessed.
  Reuse `model_adapter`'s refusals verbatim: `NO_SPEND` for stubs, `BUDGET_EXHAUSTED` when a real
  callable arrives with no tracker, fail-closed on any parse exception.
- **An adversarial stub set** — the point of the week. Stubs that return: a span not present in the
  document; a span present but at a different offset; a span off by one character; a date not
  derivable from its own span; two slots claiming overlapping spans; a slot with an empty span; a
  span present in the *prompt* but not in the *document* (the failure `model_adapter.StubModel`'s
  docstring records having actually made once). Every one must produce `UNKNOWN`.

**Founder track:** hand-label 10 documents from `corpus/testdocs/` with true slot values **and true
spans**. Labelling the span, not just the value, is what makes the harness measurable.

**Gate:** every adversarial stub yields `UNKNOWN`; `step_log` round-trips; `scripts/run_tests.sh`
green with both new modules in the suite list.

**Does not yet claim:** any extraction accuracy figure whatsoever. A harness that rejects a
fabricated span tells you the harness works. It tells you nothing about how often a model fabricates
one — that is week 5, and conflating the two would be the same error as citing the internal "31/32"
as production accuracy (`CLAUDE.md`, known-invalid results).

**Minimum ship:** `step_log.py`. Everything later depends on it.

---

### Week 5 — Wed 30 Sep → Tue 6 Oct
#### Ship: the first real model call in this project's history — extractor only, shadow, capped

**What stops being stubbed, precisely.** `checker/model_adapter.py` — the **answer** step —
**stays stubbed through both months.** It cannot ship: its serving gate is
`checker/metric_policy.evaluate_gate` passing with a real model's claims in the loop against a
benchmark, and B-001 does not exist. Shipping the answer step now would mean serving legal
conclusions scored against a 67-row internal fixture set whose own manifest says it does not measure
general legal grounding.

What stops being stubbed is **`checker/extract_adapter.py`**, and only that.

**What the first real call does.** One document, one prompt, N slots. For an AGM matter:
`{agm_date, previous_agm_date, financial_year_end, company_class_asserted, notice_date}`. It returns
per slot a value, a verbatim span, and an offset. It has no access to the Act, no access to the
obligation register, and no ability to conclude anything. It is a copying task under exact-match
verification — `docs/PROVIDER_DECISION.md` §4: *"you need obedience, not creativity"* — so it runs
at haiku tier and a stronger model is not purchased.

**What verifies its output.** Three layers, in order:

1. **Mechanical (week 4's harness, ₹0):** span present, at the stated offset, exact after
   whitespace normalisation; value re-derivable from the span by a deterministic parser. Failure →
   `UNKNOWN`. This is the layer that makes fabrication structurally impossible rather than
   statistically unlikely: a date not in the document has no span.
2. **Fixture comparison (human, week 4's 10 labelled documents):** two separate numbers, and they
   must never be reported as one —
   - **span-verification rate**: of all slots the model filled, how many survived layer 1;
   - **slot correctness on verified spans**: of the slots that survived, how many match the human
     label. A model can pass layer 1 perfectly by quoting the *wrong* date that genuinely appears in
     the document. Layer 1 catches invention. Only layer 2 catches misreading.
3. **Downstream refusal (`checker/matter.py`, exists):** `Matter` construction raises on
   contradictory facts and `missing_for_agm()` names the gap **before** any calculation. An
   extractor error that survives layers 1 and 2 still cannot silently become a legal answer.

**Shadow mode is the default and is not optional.** Extraction output is written to `step_log`,
displayed to the operator side-by-side with the document, and **not** written into a `Matter` used
for a served conclusion until layer-2 numbers exist. `checker/matrix_view` continues to take typed
facts.

**Cost, against the ₹3,500/month cap.** Reproduce with
`PYTHONPATH=. python3 -c "from backend.budget import cost_inr; print(cost_inr('claude-haiku-4-5',2000,400))"`:

| Shape | haiku-4-5 | sonnet-5 | haiku, Batch API |
|---|---:|---:|---:|
| extractor, 2,000 in / 400 out | **₹0.3809** | ₹1.1428 | ₹0.1905 |
| extractor, 4,000 in / 600 out (a long notice) | **₹0.6666** | ₹1.9998 | ₹0.3333 |
| answer, 1,800 / 700 — *not being built* | ₹0.5047 | ₹1.5142 | ₹0.2524 |

**Per matter at week 5's configuration: ₹0.3809.** One extractor call, no answer step, no narrator.
Against the ₹3,500 monthly cap that is ~9,189 matters/month; against the derived ₹116.67 daily cap,
~306 matters/day.

Four corrections to that arithmetic, all of which make it worse and none of which is modelled:

- **Retries are charged on the attempt, not the success.** A retried extraction is a second call.
- **Iteration.** `AGENT_ARCHITECTURE_PLAN` §5.4 guesses 2–4× per matter with no user data behind
  it. At 3× the figure is ₹1.14/matter and ~3,063 matters/month. That number is a **GUESS** and
  `step_log` is what will replace it with a measurement.
- **USD/INR 95.23 is dated 2026-08-06.** A weaker rupee raises every figure above.
- **Model identifiers are UNVERIFIED.** `docs/PROVIDER_DECISION.md` §7 records three prior plans
  that each named a retired identifier. Check the registry before the first call, not after it
  fails.

**The week's actual spend is trivial and that is the point.** 10 fixture documents × 3 prompt
revisions × ₹0.3809 ≈ **₹11.43**, 0.33% of one month's cap. If week 6 kills the extractor, the
abandonment cost is a rounding error.

**Budget guard:** propose a standing sub-cap of **₹500/month** for extraction — 1,312 documents at
the 2,000/400 shape — leaving ₹3,000 for whatever the answer step eventually costs. `backend/budget.py`
has one global cap; a per-task sub-cap is a small addition to `BudgetTracker` and it is what stops
a debugging loop consuming the month.

**Gate:** every call appears in `step_log` with its measured `cost_inr`; no call is made without a
tracker; the two layer-2 numbers are reported separately; nothing extracted reaches a served row.

**Does not yet claim:** that extraction is accurate; that the answer step works; that the system
reads documents in production; anything about scanned intake.

**Minimum ship:** one real call, logged, against one document — proof that the guard chain holds
end to end with money moving.

---

### Week 6 — Wed 7 Oct → Tue 13 Oct
#### Ship: the extractor's go/no-go, decided on the assumption most likely to be false

`docs/BUILD_PLAN_PRODUCT.md` assumption 12: *"Real intake is text-extractable — **UNVERIFIED and
probably false.** All 29 corpus documents are text-extractable by selection, not by sampling how
documents arrive."* `docs/WORKFLOW_BACKLOG_INDIA.md` §0.2 finding 1: four of four interviews say
documents are **physical** — *"सब physical रहते हैं"*.

The extractor's entire safety property is exact substring matching. OCR noise attacks exactly that
property. So this week answers the question rather than deferring it:

- Take the 10 labelled fixtures through a degradation path — print, photograph at phone-camera
  angle and lighting, OCR — and re-run layer 1. Also test a synthetic degradation (character
  substitution at 1%, 3%, 5%) to get a curve rather than a single point.
- Report the span-verification rate at each degradation level next to the clean baseline.

**Then decide, in writing, one of three things:**

1. **Ship out of shadow, narrowed** — extraction serves only the slots that survived, and only for
   text-extractable input, with scanned input routed to typed entry. Say which slots, say the rate.
2. **Ship in shadow only** — the operator sees a proposal, the user does not.
3. **Do not ship** — `BUILD_PLAN_PRODUCT` §8 Stage 4 already names this kill criterion: *"if real
   intake turns out to be scan-heavy and OCR error rates break exact substring matching, the
   extractor's entire safety property is unavailable and the step must not ship."* If that happens
   the correct response is to **stop**, not to relax the matcher to fuzzy. Relaxing the matcher
   converts a measurable safety property into an unmeasurable one.

There is no fourth option in which we ship it anyway and watch.

**Filler if the decision comes early:** `CA13-S173-NOTICE` — s.173(3), *"not less than seven days
notice in writing to every director"*, plus the shorter-notice proviso as a supplied fact. Act-only,
cheap, and it pairs with rows already shipped.

**Does not yet claim:** coverage beyond the slots measured; that OCR quality on our synthetic
degradation resembles a real firm's scanner.

**Minimum ship:** the written decision with its numbers. A dated no is a deliverable.

---

### Week 7 — Wed 14 Oct → Tue 20 Oct
#### Ship: the first defect measurement in this project's history

`research/TASKS.md` R-008: *"Measure scanner FALSE NEGATIVES — never measured, all corpus docs are
compliant."* This is the gap that makes every "we found nothing" indistinguishable from "there was
nothing".

- Build **15 deliberately defective documents** from the 11 ICSI specimens we hold, one seeded
  defect each, every defect of a type the register can *in principle* catch: an AGM 16 months after
  the last; no AGM at all; three board meetings in a calendar year; a >120-day board gap; a public
  company with two directors; sixteen directors and no special resolution; AOC-4 on day 45; an
  annual return on day 75.
- Each carries a label: the defect, the expected row id, the expected row state.
- Run `checker/obligations.build()` over all 15 and report, per obligation: caught,
  missed (false negative), and fired-on-the-wrong-row.

**This is not B-001 and must never be described as it.** B-001 asks for 30–50 documents *from real
practice*, labelled by *someone who is not the author of the checker*. This is 15 synthetic
documents labelled by the author of the checker. It measures **whether the register fires when it
should** — a floor. It cannot measure whether the register is *right*, because the same person wrote
the rule and the expectation. It is worth doing because a register that does not even fire on a
seeded defect is disqualified before a lawyer ever sees it, and finding that out costs a week rather
than a quarter.

**Gate:** a per-obligation false-negative count exists, and it is a number, and it is in the repo.

**Does not yet claim:** B-001; accuracy; false-positive rate (that needs compliant documents run
against the same rules, which R-003 records as still over-firing at T1.4a/T1.6a/b/c/T1.7).

**Minimum ship:** 5 defective documents against the two AGM rows.

---

### Week 8 — Wed 21 Oct → Tue 27 Oct (+ close-out Wed 28 → Sat 31 Oct)
#### Ship: the honest public statement, and the segment decision

**(a) A public page that makes only process claims.** Per `BUILD_PLAN_PRODUCT.md` §5, until all
nine preconditions hold, the permissible public statements are about *what the system refuses,
discloses, and will not say*. Concretely, and each of these is true today and checkable in the
repository:

- five row states, and "this does not apply to you" is never merged with "I cannot tell whether
  this applies to you" (`checker/obligations.py`, `ROW_STATES`);
- a threshold we have not properly acquired is refused, not guessed
  (`checker/prescribed_thresholds.lookup`, `ThresholdUnavailable`);
- a model citation to evidence outside its pack is rejected, never repaired
  (`checker/model_adapter._parse`);
- a defective government source is preserved verbatim and flagged, never corrected
  (`docs/SOURCE_DEFECTS.md`, SD-004);
- a retracted claim stays visible with the reason (`docs/RETRACTIONS.md`);
- **no accuracy claim appears anywhere**, and the page says why in one sentence.

Two prohibitions carried from `BUILD_PLAN_PRODUCT.md` §5 and `CLAUDE.md`: no claim about what a
competitor *cannot* do (absence from a marketing page is not absence from a product), and never
present student feedback as lawyer validation (`docs/EVIDENCE_PROTOCOL.md`).

**(b) R-011 — the segment contradiction gets decided in writing.** `docs/PRODUCT_SCOPE.md`, locked
20 Aug, says the buyer is a corporate lawyer and *"not a product aimed primarily at Company
Secretaries"*. `docs/WORKFLOW_BACKLOG_INDIA.md` §0.2 records that every workflow with strong in-repo
evidence — minutes, AGM notices, SS-1/SS-2, annual filings, MGT-8 — is Company Secretary work; that
our enforcement corpus penalises the *certifying* professional, a CS function; and that the one
company-side interviewee, asked unprompted, said *"CA है, company secretary"*. R-011 has been open
since 20 Aug with no progress.

The week-8 output is a decision with a reason, not a resolution of the evidence: either the declared
buyer changes to CS, or `PRODUCT_SCOPE.md` gains an explicit paragraph stating why lawyer stands
despite the evidence pointing the other way. **Four interviews cannot settle this either way** — the
decision must say so and must name what would.

**(c) Close-out, 28–31 Oct.** Re-run `scripts/run_tests.sh`. Update `research/TASKS.md` with real
status on H-001, B-001, S-002, R-003, R-008, R-011. Write the next two months' decision, informed
by whatever the five H-001 conversations actually said.

**Does not yet claim:** accuracy; any market size (R-011's model is for the wrong segment and no
figure in it may be quoted); that the segment is settled.

**Minimum ship:** the process-claims page. It is a writing task over facts that already exist.

---

### The eight weeks in one table

| Wk | Dates | Ships | Costs | Does not yet claim |
|---|---|---|---:|---|
| 1 | 2–8 Sep | s.96 all Act limbs; `CA13-S137-AOC4`; `CA13-S92-RETURN`; H-001 outreach sent | ₹0 | it knows any FY end; that a filing happened |
| 2 | 9–15 Sep | Rules 6 & 7 transcription-verified → `DEFECT_FLAGGED_PRODUCTION_LIMITED`; blocked-rows panel | ₹0 | that the rules are current |
| 3 | 16–22 Sep | `CA13-S177-AUDIT-CMTE`, `CA13-S177-9-VIGIL`; date-bound figure or explicit refusal | ₹0 | committee composition |
| 4 | 23–29 Sep | `checker/step_log.py`; `checker/extract_adapter.py`; adversarial stub set; 10 labelled fixtures | ₹0 | any extraction accuracy figure |
| 5 | 30 Sep–6 Oct | first real model call — extractor, haiku, shadow, logged | ~₹11 | that extraction is accurate; that we read documents |
| 6 | 7–13 Oct | OCR degradation measurement; extractor go/no-go **in writing** | ~₹15 | coverage beyond measured slots |
| 7 | 14–20 Oct | 15 seeded-defect documents; first false-negative count (R-008) | ₹0 | that this is B-001 |
| 8 | 21–27 Oct | process-claims page; R-011 segment decision; close-out | ₹0 | accuracy; market size |

**Total planned model spend across two months: under ₹30 of a ₹7,000 two-month allowance.** If that
looks too small, read it as the finding it is: nothing in this plan's critical path is gated on
model spend. It is gated on two human tasks (H-001, S-002) and one measurement (R-008).

---

## 4. Obligations: which, in what order, and why each earns its place

### 4.1 Shipping in these eight weeks

| # | Obligation | Wk | Rules needed | Why it earns its place |
|---|---|---|---|---|
| 1 | s.96(1) — remaining Act limbs | 1 | none | Half-built already; the gap limb alone answers a question nobody asks. The six-month and nine-month limbs are what a practitioner is actually counting to, both are verbatim in our corpus, and — since `limbs_not_decided` landed — completing them is what makes `CA13-S96-AGM` capable of showing a pass at all (§1.2). |
| 2 | s.137(1) — AOC-4, 30 days | 1 | none for the deadline | Highest value per line in the register. One subtraction off a fact already collected, and it converts a single AGM date into a second dated obligation — the chain effect `WORKFLOW_BACKLOG` W6 ranks highly and marks blocked. The *deadline* is not blocked; only the form is. |
| 3 | s.92(4) — annual return, 60 days | 1 | none for the deadline | Its "should have been held" limb makes the row decidable **when nothing happened** — the no-document row that `FEATURE_PLAN_INDIA` §0 calls the whole thesis. Also the cheapest live test of that thesis. |
| 4 | s.177(1) — audit committee | 3 | Rule 6 (held, restricted) | The first row exercising a rule we hold, and it splits into an Act limb (listed public → decidable now) and a delegated limb — proving the two-limb pattern on a real instrument before we bet a quarter on rules acquisition. |
| 5 | s.177(9) — vigil mechanism | 3 | Rule 7 (held, restricted) | Same instrument, same page range, marginal review cost near zero once Rule 6 is read. |
| 6 | s.173(3) — seven days' notice | 6 filler | none | Act-only, verbatim in corpus, pairs with `CA13-S173-BOARD` which already ships. Cheap slack-filler, not a headline. |

### 4.2 Named, and deliberately not built in these eight weeks

| Obligation | Blocked on | Notes |
|---|---|---|
| s.2(85) small company | **S-002** — G.S.R. 700(E), founder download | Already a row that correctly refuses. Unblocking it is the single highest-leverage human action available (§5.2). |
| s.173(5) relaxed regime | s.2(85), i.e. S-002 | Currently forces every private company to `APPLIES_UNDETERMINED` on board meetings rather than applying the stricter regime — the right refusal, and a large hole. |
| s.149(1) 2nd proviso (woman director), s.149(4) (independent directors) | Companies (Appointment and Qualification of Directors) Rules 2014 — **NOT HELD** | Already surfaced-never-decided in `_decide_board_size`. Do not add a third limb to that function until the instrument exists. |
| s.177(2) composition | same instrument | Depends on the definition of independent director. |
| s.203 KMP | Companies (Appointment and Remuneration of Managerial Personnel) Rules 2014 — **NOT HELD** | |
| s.138 internal audit; s.134(3) board report | Companies (Accounts) Rules 2014 — **effectively not held.** What we have is a secondary-source reproduction of one clause with an explicit `PROVENANCE_WARNING` | Must not be counted as an acquisition. |
| s.139(2) auditor rotation | Companies (Audit and Auditors) Rules 2014 — **NOT HELD** | |
| s.92(1)/(2) MGT-7 vs 7A, MGT-8 | Companies (Management and Administration) Rules 2014 — **NOT HELD** | The *deadline* ships in week 1; the *form* is refused. |
| s.188 / Rule 15 related-party | Rule 15 is held but is the **worst** artefact we have: 13,401 chars, undefined body boundary, 557 split words, and thresholds that have moved by amendment | `WORKFLOW_BACKLOG` W8 ranks this highly. It is deferred on transcription quality, not on value. |
| s.118(10) / SS-1 minutes | **R-003** — `checker/ss/defects.py` still over-fires at T1.4a, T1.6a/b/c, T1.7 | We hold SS-1 and SS-2 full text in `corpus/reference/`, so this is a *rework* item, not an acquisition item. Adding rows on top of a scanner measured at 80–93% false positives would multiply a known defect. |
| s.174 quorum | **S-001** — SD-004: India Code serves *"of a company **hall** be one-third"* and `CLAUDE.md` forbids repairing a defective government source | Needs an independent authoritative witness that does not exist. |

**The pattern worth naming:** of the ten deferred items, **one** is blocked on our code (s.118, via
R-003), **one** on a source defect (s.174), and **eight** on delegated legislation we do not
possess. Coverage is an acquisition problem, not an engineering problem — which is §5.

---

## 5. Rules acquisition

### 5.1 The bound, stated exactly

- Act sections held: **527 records / 474 mapped** (`checker/section_index.py`, 12/12 MVP sections
  verified against India Code's own REST API).
- Rule instruments held: **1** — G.S.R. 240(E) of 31-03-2014, as made, no amendment chain.
- Rule instruments **production-usable: 0**.
- Section records containing "prescribed": **174 / 527 = 33.0%** (MEASURED, crude — §1.7).

We can currently answer, at full confidence, obligations whose applicability and whose test are
both stated operatively in the Act. That is a real set — s.96, s.137, s.92(4), s.173(1), s.173(3),
s.149(1) numbers limbs, the s.177 listed-public limb — and it is roughly the eight weeks above. It
runs out immediately after.

### 5.2 The acquisition sequence

Ordered by *unblocked rows per unit of human effort*, not by importance.

| # | Instrument | Effort | Route | Unblocks |
|---|---|---|---|---|
| **A0** | Read what we already hold: Rules 6 & 7 of G.S.R. 240(E) | ~4h, founder, **no acquisition** | transcription check vs pages 15–16 of a PDF already on disk | s.177(1) prescribed limb, s.177(9). **Week 2.** The only zero-acquisition item in the list and therefore first. |
| **A1** | The **amendment chain** for G.S.R. 240(E) | founder, unknown | eGazette / India Code, per `docs/ACQUISITION_POLICY.md`; `BLOCKED` states are never auto-retried | Nothing new — it makes everything A0 unblocks *current* instead of as-made-2014. Without it every Rule 6/7 answer carries a restriction code forever. |
| **A2** | **G.S.R. 700(E)** — Specification of Definition Details Amendment Rules 2022 | founder, ~15 min *once a route exists* | Both official routes closed to automation: `indiacode.gov.in/robots.txt` returns **502** and `checker/robots.py` fails closed by RFC 9309; eGazette chains to ISRG Root YR, absent from this machine's trust store. **A human downloads the file**, then `python3 scripts/register_gsr700e.py <file>`. Instrument located: handle `123456789/508916`, bitstream `6d5e9902-…`, 5,153 bytes. | s.2(85) → s.173(5) regime for **every private company** → MGT-7A eligibility → the largest single class of currently-refusing rows. **Highest leverage action in this entire document, and it is fifteen minutes of a human's time.** |
| **A3** | Companies (Appointment and Qualification of Directors) Rules 2014 + amendments | founder | same routes | s.149(1) 2nd proviso, s.149(4), s.177(2) composition, DIR-3 KYC (which R-005 has already found one SUPERSEDED claim about) |
| **A4** | Companies (Management and Administration) Rules 2014 | founder | same | MGT-7 vs 7A selection, MGT-8 certification threshold — completes the week-1 rows |
| **A5** | Companies (Accounts) Rules 2014 — **proper gazette**, replacing the secondary reproduction | founder | same | s.134(3) board report, s.138 internal audit; and retires a `PROVENANCE_WARNING` that currently sits in the corpus |
| **A6** | Companies (Audit and Auditors) Rules 2014 | founder | same | s.139(2) auditor rotation |

### 5.3 Two rules about this sequence that are not negotiable

1. **A1 outranks A3–A6 in principle even though it unblocks nothing new.** Serving as-made-2014
   rules as current law is the precise failure this product claims to detect in competitors'
   templates (`CLAUDE.md`, "The wedge"). Doing it ourselves, even under a restriction code, is the
   most embarrassing available outcome. If A1 cannot be completed, the honest fallback is to move
   Rules 6 and 7 back out of `SERVABLE_STATES`.
2. **A `BLOCKED` source is never re-probed automatically.** `docs/ACQUISITION_POLICY.md` records
   that this repo already scheduled an automated retry against a WAF that had explicitly refused
   us. `provenance.RETRYABLE` is `(UNREACHABLE,)` and the tests pin it there. Escalate to a human
   or a permitted alternative source; never to more requests.

---

## 6. The extraction stage, in one place

Consolidated from §3 weeks 4–6 because this is the question the plan is most likely to be
misread on.

**When `model_adapter` stops being stubbed: it does not, inside these two months.** The answer
step's serving gate is `checker/metric_policy.evaluate_gate` PASSing with a real model's claims in
the loop — false accepts ≤ 10, F1 ≥ 0.40, abstention ≤ 0.25, per-bucket reported, no bucket
regressing against the deterministic baseline. B-001 does not exist, and
`BUILD_PLAN_PRODUCT.md` §5 point 4 records that two of the three current buckets *cannot measure
the axis the gate exists to protect* (`dropped_qualifier` has no positives, `paraphrase` has no
negatives). A gate that cannot fail is not a gate.

**What does stop being stubbed: `checker/extract_adapter.py`, week 5, in shadow.** First real call:
one document, five slots, value + verbatim span + offset, haiku tier, behind
`backend.budget.BudgetTracker`, every call written to `checker/step_log.py`.

**What verifies it:** mechanical span verification (₹0, catches invention because a date not in the
document has no span) → human fixture comparison on 10 hand-labelled documents, reporting
span-verification rate and slot-correctness-on-verified-spans **as two numbers** → `checker/matter.py`'s
existing refusal of contradictory or half-populated matters.

**Cost per matter against the ₹3,500/month cap:** **₹0.3809** at week 5's configuration
(1 extractor call, haiku, 2,000/400) — ~9,189 matters/month, ~306/day against the derived ₹116.67
daily cap. At the unmeasured 3× iteration guess, ₹1.14 and ~3,063/month. Retries charged on the
attempt. Two-month planned spend across all extraction work: **~₹30**.

**The decision that actually matters is week 6's, and it is a no-go by default.** If OCR breaks
exact substring matching, the extractor's safety property is unavailable and the step does not ship.
The matcher is not relaxed to fuzzy to rescue it.

---

## 7. Risk register

Likelihood bands are **engineering judgement, not measurement**, and are labelled so. "How we would
know" names a detector that exists or is built in one of the eight weeks — a risk with no detector
is a risk we would find out about from a customer.

---

### RISK-01 — The extractor hallucinates a fact into a legal conclusion
**What goes wrong.** The model returns a date that is not in the document, or reads the wrong date,
and it propagates into a `Matter` and out as a dated obligation the user relies on.
**Likelihood.** Invention: **low** by construction — layer 1 makes it structurally impossible, not
statistically unlikely, because a fabricated date has no span. Misreading (a real date from the
wrong place): **medium-high, unmeasured.** These are different failures and only the first is
solved.
**How we would know.** Week 4's adversarial stub set proves layer 1 rejects invented spans. Week 5's
layer-2 fixture comparison is the only thing that measures misreading; `step_log` retains every raw
output for audit.
**Mitigation.** Exact-match span verification after whitespace normalisation only, never fuzzy.
Failure → `UNKNOWN`, never repaired. Shadow mode until layer-2 numbers exist. `matter.Matter` raises
on contradiction. Two reported numbers, never one.
**Residual.** A plausible wrong date that survives both layers reaches the user. The register still
shows its basis and the span it came from, so the error is *visible*, which is the most this design
offers. Accepted, and it is the reason the extractor stays out of the served path in week 5.

---

### RISK-02 — Unacquired rules bound coverage below usefulness
**What goes wrong.** 33% of section records point at delegated legislation; we hold one instrument,
unreviewed, as-made-2014, zero production-usable. The matrix refuses so often that practitioners
read it as broken rather than careful.
**Likelihood.** **High — this is already happening.** `CA13-S2-85-SMALL` refuses today, and through
it every private company's `CA13-S173-BOARD` row.
**How we would know.** Week 1's H-001 outreach: five practitioners shown a matrix for a company they
know. `BUILD_PLAN_PRODUCT.md` §8 already names this as *"the highest-probability kill in the list"*
and measurable in a week with five conversations.
**Mitigation.** §5's sequence, with A2 (G.S.R. 700(E), 15 human minutes) first among acquisitions.
Ship only Act-operative obligations in weeks 1–3 so the visible product grows while acquisition is
blocked. The week-2 blocked-rows panel makes refusal *legible* — naming the missing instrument and
the task id — rather than a blank cell.
**Residual.** If A2 stays blocked another quarter, `BUILD_PLAN_PRODUCT.md` §8's strategy-level kill
applies: narrow the product publicly to class-independent obligations and say so.

---

### RISK-03 — Serving as-made-2014 rules as if they were current
**What goes wrong.** Rules 6 and 7 are promoted in week 2 and a user reads a Rule 6 threshold as
today's law. We would have committed, in our own product, the exact defect our positioning says we
detect in everyone else's templates.
**Likelihood.** **Medium-high.** A restriction code in a data structure is not the same as a
sentence a reader notices — the same gap `BUILD_PLAN_PRODUCT.md` §8 names for `MODEL_SUGGESTION`
prose.
**How we would know.** Show a Rule-6-dependent row to an H-001 reviewer and ask what version of the
rule they think they are reading. If they say "current", the label failed.
**Mitigation.** `DEFECT_FLAGGED_PRODUCTION_LIMITED` + `restriction_codes=("AS_MADE_2014_AMENDMENT_
CHAIN_UNACQUIRED",)`, never `PRODUCTION_USABLE`; the restriction rendered in the row basis in
words, not as a code; A1 prioritised above A3–A6 despite unblocking nothing new.
**Residual.** If the label does not land, the fallback is to move R6/R7 out of `SERVABLE_STATES`
and lose s.177 entirely. That is an acceptable loss and is written into §8 as a kill criterion.

---

### RISK-04 — No lawyer has validated anything (H-001)
**What goes wrong.** The obligation register is materially wrong — an obligation misstated, a
proviso missed, an applicability test inverted — and no one qualified has looked. Every downstream
week compounds it.
**Likelihood.** That *some* error exists: **high**. Four obligations, one author, zero legal review.
**How we would know.** We would not, currently. That is the risk. `research/TASKS.md` H-001:
evidence **zero**. The benchmark's one reviewer is `reviewer-01`, a pseudonymous id not recorded as
a practising lawyer.
**Mitigation.** H-001 outreach moves to **week 1**, not week 6, because it is the longest-lead item
in the plan and it is a human task. Five named practitioners, `docs/validation_kit.html`. Every row
already carries its provision and its basis, so a reviewer can disagree with a specific sentence
rather than with a black box. No accuracy claim anywhere until it closes.
**Residual.** Five conversations is not a review programme. If reviewers find the register
materially wrong, `BUILD_PLAN_PRODUCT.md` §8's strategy kill applies: effort moves from code to
legal authoring, and this plan's weeks 3–7 are the wrong weeks.

---

### RISK-05 — No real-document benchmark (B-001)
**What goes wrong.** We ship, and cannot say whether we are right, forever. Marked **CRITICAL PATH**
in `research/TASKS.md`.
**Likelihood.** That it stays open past 31 Oct: **high.** It needs 30–50 real documents including
defective ones, labelled by a non-author; we hold 29, all compliant, zero minutes books, none
public.
**How we would know.** It is a ledger row. It is open.
**Mitigation.** Week 7's 15 seeded-defect documents give a **false-negative floor** — the R-008
number that has never existed — for the cost of one week. It is explicitly *not* B-001 and the plan
says so in the same paragraph that announces it.
**Residual.** Everything. A synthetic set labelled by the checker's author cannot measure
correctness. No accuracy claim is permitted at 31 Oct and none is planned.

---

### RISK-06 — Solo-founder capacity
**What goes wrong.** Eight distinct shippable weeks, one person, and weeks 1, 2, 4 and 7 each carry
a founder task (outreach, transcription, labelling, defect authoring) *on top of* the code. One bad
week cascades and the plan quietly becomes fiction — which is what happened to the five plans that
preceded this one.
**Likelihood.** **High.** This is the most likely failure mode in the register.
**How we would know.** Immediately: each week names a **minimum ship**, and a week that does not
reach its minimum is a signal on the day, not at the end of October.
**Mitigation.** Every week has a minimum ship, deliberately chosen to be the item everything else
depends on (week 4's is `step_log.py`; week 6's is a written decision, so even a no-go is a
delivery). The founder tasks are separated from the legal-judgement tasks so they do not wait on
H-001 — transcription checking is eyes, not law. Week 8's close-out has four days of slack and no
new code. Total planned model spend under ₹30, so no week is gated on procurement.
**Residual.** If two consecutive weeks miss their minimum, the correct response is to cut weeks 3
and 7 and finish weeks 4–6 and 8. Recorded here so the cut is a decision rather than a drift.

---

### RISK-07 — A well-funded competitor enters Indian corporate compliance
**What goes wrong.** Legora and Harvey both ship agentic execution, bulk document workspaces,
research-with-citations and monitoring surfaces today (`docs/COMPETITOR_FEATURE_MATRIX.md`, vendor
primary sources, 2026-09-01). Against that, our column reads NONE / NONE / PARTIAL. If either
localises to Indian statutory currency, the differentiator this plan spends eight weeks on
evaporates.
**Likelihood.** Genuinely unknown, and **no claim is permitted** about what either can or cannot do
— absence from a marketing page is not absence from a product (`CLAUDE.md`; `COMPETITOR_FEATURE_MATRIX.md`
reading discipline).
**How we would know.** Vendor primary sources only, re-read quarterly. We hold no signal better than
that and must not pretend otherwise. Web search is exhausted this session, so no check was made
today.
**Mitigation, and it is thin.** Our only defensible asymmetry is the acquisition and dating of
Indian delegated legislation and the refusal machinery around it — the work in §5, which is
unglamorous, human-gated, and does not fall out of a larger model. **That is an argument for
prioritising §5 over more features, which is what this plan does.** Note the uncomfortable
corollary: our advantage is a corpus a well-funded team could buy or licence faster than we can
acquire it. There is no moat here that money cannot cross; there is only a head start on work
nobody has bothered to do.
**Residual.** Substantially unmitigated. The honest position is that this is a bet on a segment too
small and too regulatory-specific to attract a well-funded entrant soon, and that bet is
**UNVERIFIED**.

---

### RISK-08 — The segment contradiction: scope says lawyer, evidence says Company Secretary
**What goes wrong.** We build eight weeks of Company-Secretary-shaped features — AGM notices, board
meetings, annual filings, audit committees — while `docs/PRODUCT_SCOPE.md` declares the buyer a
corporate lawyer and explicitly not a CS. Then H-001 recruits lawyers, who tell us this is not their
work, and the validation measures the wrong people.
**Likelihood.** **High that the tension bites in these eight weeks specifically**, because weeks 1,
3 and 7 are all filing-and-meeting workflows, which is CS work by the backlog's own reading.
**How we would know.** Week 1's five conversations. Ask what the person's role is *before* asking
whether the matrix is useful, and record both. `research/CLAIMS_TO_TEST.md` T5/T6 (filings per
quarter, minutes sets per year) discriminate between the segments in one question each.
**Mitigation.** Recruit both — at minimum two lawyers and two Company Secretaries among the five —
and record role and PQE per `docs/EVIDENCE_PROTOCOL.md`. Week 8 forces a written decision.
No market figure is quoted externally while R-011 is open.
**Residual.** Four interviews with zero corporate lawyers and zero CSs cannot settle this. Even the
week-8 decision will be a *reasoned* choice, not an evidenced one, and it must say so.

---

### RISK-09 — Rows are being added faster than rows are being validated
**What goes wrong.** The register goes from 4 obligations to 8 in six weeks while the number
reviewed by anyone qualified stays at 0. We widen the surface over which we cannot say whether we
are right — the exact objection `AGENT_ARCHITECTURE_PLAN.md` §8 raises against Stage 5.
**Likelihood.** **Certain.** It is what §3 plans to do.
**How we would know.** By counting: obligations shipped versus obligations reviewed. Track both in
`research/TASKS.md`.
**Mitigation, and it is a genuine trade-off rather than a fix.** Every row added in weeks 1–6 is
either pure date arithmetic over statutory text quoted verbatim from our own corpus (s.96, s.137,
s.92, s.173(3)) or splits into an Act limb plus an explicitly-restricted delegated limb (s.177) —
the narrowest class of new row available. No row added depends on a model. And the same five
practitioners reviewing four rows can review eight for close to the same effort, so shipping the
rows *before* week 1's outreach lands is defensible.
**Residual.** If H-001 finds the four existing rows wrong, the four new ones are likely wrong the
same way. Accepted knowingly.

---

### RISK-10 — Real intake is scanned, and the extractor's safety property does not survive OCR
**What goes wrong.** Exact substring matching is the whole safety property. OCR noise breaks it.
Then either most slots return `UNKNOWN` (extraction is slower than typing) or we relax the matcher
(the safety property is gone and we no longer know it).
**Likelihood.** **High.** `BUILD_PLAN_PRODUCT.md` assumption 12 calls text-extractable intake
*"UNVERIFIED and probably false"*; four of four interviews say documents are physical; all 29 corpus
documents are text-extractable, which makes our corpus the opposite of what our users describe.
**How we would know.** Week 6, explicitly: degradation curve at 1%/3%/5% character substitution plus
a print-photograph-OCR round trip, span-verification rate reported at each level.
**Mitigation.** Test it in week 6 rather than discovering it in production; the go/no-go defaults to
no-go; the matcher is never relaxed to fuzzy; typed entry (`matrix_view`) remains a complete product
that costs ₹0 and has no OCR dependency at all.
**Residual.** If it fails, weeks 4–6 produced a harness, a step log and a documented no — roughly
₹26 and three weeks. That is the cost of finding out, and it is cheap.

---

### RISK-11 — The corpus is single-source and NOT_FULLY_VERIFIED
**What goes wrong.** Every provision this plan cites comes from India Code. `CLAUDE.md` records the
cross-render check as PASS_WITH_DEFECTS with two confirmed defects and independent-publisher
verification **PENDING** — both renderings compared were India Code, so a defect in their own source
is invisible to that check. SD-004 (*"of a company hall be one-third"*) proves the defects are real
and that phrase-matching silently misses qualifiers because of them.
**Likelihood.** That further defects exist in sections we rely on: **medium**. That one lands on
s.96, s.137, s.92 or s.177 specifically: **low but unquantified**.
**How we would know.** `scripts/verify_section_index.py` checks numbering against India Code's own
API — same source, so it cannot catch this class. Only an independent publisher can, and H-002
(Indian Kanoon at ₹10,000/month) exceeds the entire ₹3,500 budget.
**Mitigation.** Every week-1 and week-3 row cites text quoted verbatim in this document, so a defect
in the quoted phrase is visible to any reader who compares. Defects are preserved verbatim and
flagged, never repaired (`docs/SOURCE_DEFECTS.md`). H-002's free non-commercial tier application is
unfiled and remains a founder action.
**Residual.** Corpus status stays `NOT_FULLY_VERIFIED` at 31 Oct, and it is one of the nine
preconditions in §9 that no accuracy claim may skip.

---

### RISK-12 — Cost and pricing assumptions drift
**What goes wrong.** `USD_INR = 95.23` is dated 2026-08-06 and stale by four weeks; model
identifiers in `backend/budget.PRICING` are **UNVERIFIED** and `docs/PROVIDER_DECISION.md` §7
records three prior plans that each named a retired identifier. Week 5's first real call fails on an
unknown model id, or the budget guard silently under-estimates.
**Likelihood.** Of an id problem on first call: **medium.** Of material budget drift in two months:
**low** — planned spend is under ₹30.
**How we would know.** `cost_inr()` raises `ValueError` on an unknown model rather than guessing;
`step_log` records measured cost per call against the estimate.
**Mitigation.** Check the model registry before writing the week-5 call, not after. List prices kept
deliberately (*a budget guard must only ever be wrong in the expensive direction*). Refresh USD/INR
and re-run `python3 backend/budget.py` in week 5. Propose a ₹500/month extraction sub-cap.
**Residual.** Trivial at this spend level. It becomes real only when the answer step ships, which is
not in these two months.

---

### RISK-13 — The matrix's central bet is wrong
**What goes wrong.** `FEATURE_PLAN_INDIA.md` §0's whole inversion is that the most valuable rows are
the ones with **no document behind them**. `BUILD_PLAN_PRODUCT.md` assumption 11 marks this
**UNVERIFIED and central**. If practitioners read no-evidence rows as noise, the architecture is
correct and the product is not.
**Likelihood.** Unknown, and it is the single most consequential unknown in this plan.
**How we would know.** Week 1's five conversations, and cheaply: `CA13-S92-RETURN`'s "should have
been held" limb is built in week 1 precisely because it is a no-document row a practitioner can
react to.
**Mitigation.** Build the cheapest possible test of the bet in week 1 rather than the most
impressive version of it in week 6.
**Residual.** If the bet is wrong, the register survives as an internal correctness device and the
*product* is something else. That is a re-plan, and `BUILD_PLAN_PRODUCT.md` §8 already names it as
a Stage 1 kill.

---

### RISK-14 — s.52(1)(q)(ii): serving Act text without original matter
**What goes wrong.** `checker/matrix_view.py`'s docstring commits to never rendering a provision's
text as its own content, with a test asserting the card carries no bare statutory extract. Weeks 1–3
add rows whose basis strings quote statutory phrases ("within thirty days", "not less than seven
days"), and week 8 publishes a page. Quoting drifts past what the posture allows.
**Likelihood.** **Medium**, and it is a drift risk rather than a decision risk — nobody will decide
to breach it; it will happen one basis string at a time.
**How we would know.** The existing `matrix_view` test. Extend it to every new row's basis in weeks
1 and 3.
**Mitigation.** Basis strings state our *analysis and the deadline*, with short attributed phrases,
never a provision reproduced as content. `FEATURE_PLAN_INDIA.md` §6 holds the consolidated posture
and this plan does not reopen it. The operating assumption stays the conservative one, and whether
machine-generated commentary satisfies the section is a **counsel question, unverified,
human-gated**.
**Residual.** Unresolved legal question, deliberately.

---

### Risk register, ranked by expected damage

| Rank | Risk | Likelihood (judgement) | Damage if it lands | Detector exists? |
|---|---|---|---|---|
| 1 | RISK-06 solo capacity | High | The plan becomes the sixth unexecuted plan | Yes — weekly minimum ship |
| 2 | RISK-04 no lawyer validation | High (that some error exists) | Everything built is unassertable | **No — built in week 1** |
| 3 | RISK-02 unacquired rules | High (already live) | Product reads as broken | Yes — week 1 conversations |
| 4 | RISK-13 the central bet | Unknown | Architecture right, product wrong | Yes — week 1, cheaply |
| 5 | RISK-10 OCR breaks extraction | High | Weeks 4–6 wasted (~₹26) | Yes — week 6 |
| 6 | RISK-08 segment contradiction | High | Validating the wrong people | Partial — week 1 role capture |
| 7 | RISK-05 no benchmark | High it stays open | No accuracy claim, ever | Yes — it is a ledger row |
| 8 | RISK-03 as-made-2014 rules | Medium-high | Our own positioning inverted | Yes — week 2 label test |
| 9 | RISK-01 extractor misreads | Medium-high (misread) | A wrong dated obligation | Partial — week 5 layer 2 |
| 10 | RISK-09 rows outrun validation | Certain | Compounding unvalidated surface | Yes — count both |
| 11 | RISK-07 funded competitor | Unknown | Differentiator evaporates | **Weak — vendor pages only** |
| 12 | RISK-11 single-source corpus | Medium | A cited provision is defective | Weak — same-source only |
| 13 | RISK-14 s.52(1)(q)(ii) drift | Medium | Legal exposure on the public page | Yes — extend existing test |
| 14 | RISK-12 cost/pricing drift | Medium (ids) | A failed first call | Yes — `cost_inr` raises |

---

## 8. Kill criteria, per stage of this plan

`docs/BUILD_PLAN_PRODUCT.md` §8 holds the kill criteria for the six product surfaces and is not
restated. These are the kill criteria for **the eight weeks**, written now so they cannot be
renegotiated in October.

**Weeks 1–3 — the Act-only obligations.**
Kill or re-plan if, of five practitioners shown a matrix for a company they know, **fewer than three
can name an obligation the register missed**. Complete-looking and incomplete is worse than
obviously thin. The inverse also kills it: if all five name five or more misses each, this is a stub,
not a product.
Kill the s.177 rows specifically if an H-001 reviewer, shown a Rule-6-dependent row, believes they
are reading current law. Then the restriction label has failed, R6/R7 come out of `SERVABLE_STATES`,
and s.177 is lost until A1 completes.

**Week 2 — rules review.**
Kill the whole "read what we hold" approach if transcription verification of two rules (2,315 chars,
99 split words) takes more than one working week. At that rate the remaining 13 rules are ~5 weeks
of a founder's time for one 2014-vintage instrument, and the acquisition strategy in §5 is
unaffordable at solo scale. The correct response is to buy or commission clean text, not to grind.

**Weeks 4–6 — the extractor.**
Kill if the OCR degradation curve shows span verification collapsing at realistic noise (week 6).
Kill if most slots return `UNKNOWN` on clean documents, making extraction slower than typing.
Kill if the two layer-2 numbers cannot be produced — because a step whose output cannot be scored is
a step that cannot be gated.
**Do not respond to any of these by buying a bigger model.** `BUILD_PLAN_PRODUCT.md` §8: buying
up-tier converts a correctness failure into a cost failure and hides it.

**Week 7 — the defect measurement.**
Kill the register's design if it misses more than half of 15 seeded defects of types it claims to
cover. That would mean the applicability logic is not reaching the rows at all.
Equally: if it fires on rows it should not, R-003's over-firing has spread beyond `checker/ss/` into
the obligation register, and the register — not the scanner — becomes the priority.

**Week 8 — the public statement.**
Kill the page if it cannot be written without an accuracy claim. If the honest process claims are
not interesting enough to publish, that is a finding about the product, not about the writing.

**Kill criteria for this plan as a whole.**
- **If two consecutive weeks miss their minimum ship**, stop adding weeks. Cut weeks 3 and 7, finish
  4–6 and 8.
- **If H-001 produces zero responses by 30 September** (four weeks after outreach), the constraint
  is distribution, not engineering, and October should be spent on reaching practitioners rather
  than on the extractor. This is the criterion most likely to fire and the one most likely to be
  ignored.
- **If S-002 is still blocked on 31 October** — five months after the instrument was located —
  `BUILD_PLAN_PRODUCT.md` §8's strategy kill applies: narrow the product publicly to obligations
  that do not depend on company class, and say so.
- **If B-001 later shows the deterministic core is not more accurate than a frontier model answering
  the same questions directly**, the entire thesis is dead. That measurement does not exist and
  nothing in these eight weeks creates it. Recorded so the plan can be wrong.

---

## 9. Market evidence: status of every figure

**Rule applied throughout, from the runbook: these may be used as hypotheses to test. They may not
be used as evidence, and none of them is load-bearing for any week in §3.**

### 9.1 The Manupatra 2025 survey — every figure UNVERIFIED

Verification was attempted and failed: the published PDF is a Canva design export whose text layer
carries glyph codes with no ToUnicode CMap, so neither WebFetch nor `checker/pdf_text.extract_text`
can read it. Web search budget is exhausted (200/200), so no secondary source could be checked. The
survey's own stated limits would still apply if it were verified: **227 respondents including
students is directional, not a census.**

| Figure as supplied | Status | Treated in this plan as | Testable how, and when |
|---|---|---|---|
| 87.63% experienced or heard of AI errors in legal matters | **UNVERIFIED** | Hypothesis. "Heard of" and "experienced" are different populations and the composite is not usable either way. | Not testable by us. Ignored. |
| Only 4.07% fully trust AI output; 48.84% trust only with human verification; 36.63% consider it risky | **UNVERIFIED** | Hypothesis, and the one closest to our design bet — RISK-13 and `BUILD_PLAN_PRODUCT.md` assumption 13 (that practitioners prefer a visible refusal to a confident unsourced number). | Week 1 conversations, and `CLAIMS_TO_TEST.md` **B4** (observe whether they open a citation) — which is behavioural and therefore stronger than the survey. |
| 58.14% cite unreliable output quality; 51.16% hallucinated or wrong content | **UNVERIFIED** | Hypothesis. | Week 1, as an open question, never as a leading one. |
| 42.44% inadequate Indian-law support | **UNVERIFIED** | Hypothesis most flattering to our positioning, and therefore the one to distrust most. | Week 1: ask what they last could not find, not whether Indian support is adequate. |
| 47.67% data-security/privacy; 28.49% client-confidentiality; 38.37% ethical concern | **UNVERIFIED** | Hypothesis. Note `scripts/serve_matrix.py` already binds 127.0.0.1, logs no query strings, and sends nothing off the machine — an architecture consistent with this concern that was chosen for other reasons. | Week 1. If real, it is an argument for local-first, which we already are. |
| 79.65% report time savings on repetitive tasks | **UNVERIFIED** | Hypothesis. | `CLAIMS_TO_TEST.md` T5/T6 measure volume, which is the precondition for time saving. |
| 66.52% want free/freemium access | **UNVERIFIED** | Hypothesis, and if true it is a **problem**, not an opportunity, against a ₹3,500/month budget and `CLAIMS_TO_TEST.md` P1's ₹9,999/mo persona claim. | Week 8's pricing note, if week 1 produces any willingness-to-pay signal. Zero interviews currently record one. |
| 67.40% want training/certification | **UNVERIFIED** | Hypothesis. Out of scope. | Not tested. |
| 43.61% want case-management integration | **UNVERIFIED** | Hypothesis. Cuts **against** this plan: we build no integrations in eight weeks. | Week 1: ask what system the answer has to end up in. |

**No week in §3 changes if every one of these figures is false.** That is deliberate and is the test
of whether the plan is grounded in code rather than in market narrative.

### 9.2 NJDG pendency — better sourced, and measuring the wrong thing

As supplied, at 10 Feb 2026: 92,320 Supreme Court; 63,62,174 High Courts; 4,81,60,880
district/subordinate. Attributed to Department of Justice material.

**Status: BETTER SOURCED THAN THE SURVEY, NOT INDEPENDENTLY VERIFIED HERE** (no web access this
session). And more importantly:

> **It measures court backlog, not demand for software — and specifically not demand for the
> software this repository builds.** Our wedge is corporate compliance under the Companies Act 2013
> (`CLAUDE.md`, "Current focus"), which is transactional and calendar-driven. It is not litigation.
> A district-court queue of 4.8 crore cases says nothing about whether a Company Secretary will pay
> for an AGM deadline card. Litigation features are explicitly out of scope in the runbook.

Permitted use: as context for "Indian legal services are under load". Forbidden use: as a market
size, a TAM input, or a demand signal for this product.

### 9.3 What we actually know about users — VERIFIED, and thin

From `docs/WORKFLOW_BACKLOG_INDIA.md` §0.1, which is in-repo and checkable: **4** practitioner
interviews, of which **0** corporate lawyers, **0** Company Secretaries; 42 comments from 16
authors, 62% by one author; **0** interviews recording a workflow frequency, a task duration, or a
willingness to pay.

**Every "frequency" anywhere in our planning is ASSUMED**, either from the statute (the Act fixes
how often an AGM happens — a fact about the law, not about a practitioner's week) or from
enforcement data (how often the ROC penalises a defect, which is not how often anyone does the
work). `research/CLAIMS_TO_TEST.md` is explicit that its persona-derived claims are hypotheses from
a simulation, not evidence.

---

## 10. What must be true before any accuracy claim is made publicly

`docs/BUILD_PLAN_PRODUCT.md` §5 already lists nine conditions and **all nine still stand
unchanged**. They are not restated here. What this section adds is the status of each on
**31 October 2026 as this plan is written**, so the answer to "can we say it yet" is a table lookup
rather than an argument:

| # | Condition (short form, per §5) | Projected status at 31 Oct 2026 |
|---|---|---|
| 1 | B-001 exists — 30–50 real documents incl. defective, non-author labelled | **NO.** Week 7 gives 15 synthetic, author-labelled. |
| 2 | False negatives measured (R-008) | **PARTIAL.** A floor exists, on synthetic documents only. |
| 3 | R-003 closed — the SS scanner no longer over-fires | **NO.** Not touched in these eight weeks, deliberately. |
| 4 | Both labels present in every scored bucket | **NO.** `dropped_qualifier` still has no positives; `paraphrase` no negatives. |
| 5 | Benchmark not 54/69 constructed, not five sections, not one reviewer | **NO.** |
| 6 | H-001 done — 1–2 practising corporate lawyers, role and PQE recorded | **UNKNOWN.** Outreach in week 1; five conversations is the target, and five conversations is not a review programme. |
| 7 | Independent-publisher corpus verification | **NO.** Both renderings are India Code; H-002 exceeds the budget. |
| 8 | Reconstruction claimed at span level only | **YES** — already the case (24 spans, 0 conflicts, `docs/CORROBORATION.md`). |
| 9 | Any claim names its scope in the same sentence | **YES**, as a discipline. |

**Conclusion, stated so it cannot be softened later: on 31 October 2026 the answer is no.** One of
nine conditions is clearly met, one partially, one is unknown, six are not. The permissible public
statements at the end of these eight weeks are the process claims in week 8(a), and nothing else.

Three additions specific to this plan:

10. **No claim may rest on a Rule in `DEFECT_FLAGGED_PRODUCTION_LIMITED` without naming the
    restriction in the same sentence.** "We check audit committee applicability" is not permissible
    while Rule 6 is as-made-2014; "we check it against the 2014 principal rules, and the amendment
    chain is unacquired" is.
11. **No extraction figure may be quoted without both numbers** — span-verification rate and
    slot-correctness-on-verified-spans — and the fixture count (10) beside them.
12. **Week 7's number is a false-negative floor on synthetic documents.** It may never be described
    as accuracy, as a benchmark, or as B-001.

---

## 11. Adversarial critique, and what survived it

Per the runbook, the draft above was attacked. Objections that did not survive are gone. These
survived, and the plan text was changed to answer them — the changes are named, not asserted.

**O1 — "You add four obligations before anyone has validated the four that exist."**
*Survived.* Answered in RISK-09 and by moving H-001 outreach from a late week to **week 1**. The
remaining defence is that every row added is either pure date arithmetic over text quoted verbatim
in §2, or splits into an Act limb plus an explicitly restricted delegated limb. It is a real
trade-off, taken knowingly, and it is a named kill criterion.

**O2 — "Weeks 4–6 spend three of eight weeks on an extractor whose core input assumption is
recorded in your own documents as 'probably false'."**
*Survived, and changed the plan.* Week 6 was rewritten from a footnote into a dated go/no-go with a
degradation curve and a default of no-go. Week 5's spend was capped at ~₹11 so abandonment costs
almost nothing. The residual argument for doing it at all: the harness (`extract_adapter`) and the
log (`step_log`) are prerequisites for **any** later model work and survive the extractor's death.

**O3 — "Verifying 1,300 split words across 15 rules in one week, solo, is a wish, not a plan."**
*Survived, and changed the plan.* Week 2's deliverable was cut from 15 rules to **Rules 6 and 7
only** (2,315 chars, 99 split words, pages 15–16). The other 13 stay `HUMAN_REVIEW_PENDING` with
their warnings intact, and Rule 15 — 13,401 chars with an undefined body boundary — is explicitly
out of both months. A kill criterion was added: if two rules take more than a week, the acquisition
strategy is unaffordable at solo scale and the response is to commission clean text, not to grind.

**O4 — "Promoting as-made-2014 rules to a servable state is the exact defect your positioning says
you detect in competitors."**
*Survived and was not fully answered.* RISK-03 exists, the destination state is
`DEFECT_FLAGGED_PRODUCTION_LIMITED` rather than `PRODUCTION_USABLE`, the restriction code is
rendered in words, A1 was ranked above A3–A6 despite unblocking nothing new, and a kill criterion
was added that removes R6/R7 from `SERVABLE_STATES` if a reviewer reads them as current. The
tension is genuine and remains.

**O5 — "Eight weeks of work and the exit condition is still 'no accuracy claim'. What was it
for?"**
*Survived, and the answer is uncomfortable but correct.* The accuracy claim is gated on B-001 and
H-001, both founder tasks, and no quantity of engineering substitutes for either. What changes over
eight weeks is that both acquire dates and detectors, the register roughly doubles on Act-only
ground, the first false-negative number in the project's history exists, the first real model call
is made behind a harness that can reject it, and the segment contradiction gets decided instead of
carried. §10's table is deliberately a list of noes: a plan whose end state is "still cannot claim
accuracy" is either honest or pointless, and the case that it is honest is that every one of the
nine conditions is someone's dated task rather than a hope.

**O6 — "The AGM-season framing is a story you told yourself."**
*Partially survived, and changed the text.* §2 was rewritten to separate what is VERIFIED (the three
deadlines, verbatim from our corpus) from what is ASSUMED (that this company's year ends 31 March;
that practitioners feel it now). The framing was demoted from a justification to a coincidence worth
exploiting in outreach. The obligation ordering in §4 stands on the rules-dependency argument alone
and does not need the season.

**O7 — "You are using the Manupatra numbers as scaffolding while labelling them unverified."**
*Survived, and forced a test.* §9.1 now carries a column stating how each figure would be tested and
when, and §9's opening asserts — checkably — that no week in §3 changes if every figure is false.
That assertion is the answer to the objection: if it were untrue, some week would cite a survey
number, and none does.

**O8 — "The competitor risk mitigation is 'keep doing what we are doing'."**
*Survived, largely unanswered, and the text was made blunter rather than better.* RISK-07 now states
plainly that our advantage is a corpus a funded team could buy faster than we can acquire it, that
there is no moat money cannot cross, and that the whole position rests on an UNVERIFIED bet that the
segment is too small and too regulatory-specific to attract one soon. No mitigation was invented to
make this look better.

**O9 — "Week 7's synthetic corpus is B-001 theatre."**
*Survived, and the text was made to say so three times.* It is 15 author-labelled synthetic
documents; it measures whether the register fires, not whether it is right; and §10 condition 12
forbids ever describing it as accuracy or as a benchmark. The case for doing it anyway is that a
register that does not fire on a seeded defect is disqualified before a lawyer sees it, and one week
is cheap insurance against spending a quarter on rows that never trigger.

---

## 12. Assumptions declared in this document

Collected so they can be attacked in one place. `docs/BUILD_PLAN_PRODUCT.md` §9's fifteen
assumptions all still stand and are not repeated.

| # | Assumption | Status |
|---|---|---|
| A | 31 March financial year end for the §2 dates | **ASSUMED.** s.2(41) default, not universal. Code must never assume it; `Evidence.financial_year_end` stays `None` until told. |
| B | "174/527 records contain 'prescribed'" bounds our Act coverage | **MEASURED but crude.** Over- and under-counts in ways named in §1.7. Never quote externally. |
| C | Transcription verification of two rules fits in one founder-week | **ESTIMATE**, from 2,315 chars / 99 split words. Week 2's kill criterion tests it directly. |
| D | Rule 6/Rule 7 as held are substantively the 2014 as-made text | **ASSUMED** until week 2's page comparison. `production_usable` is currently `false` precisely because nobody has checked. |
| E | G.S.R. 240(E) has been amended since 2014 | **ASSUMED, and near-certain.** We hold no amendment chain and made no web check this session. If it turns out unamended, RISK-03 shrinks and A1 becomes cheap. |
| F | Haiku-tier extraction is adequate for span copying | **UNMEASURED.** `PROVIDER_DECISION.md` argues obedience over reasoning; week 5 is the first test. |
| G | ~₹11 of fixture calls suffices for week 5 | **ESTIMATE.** 10 documents × 3 prompt revisions at ₹0.3809. A fourth revision costs ₹3.81. |
| H | Synthetic OCR degradation resembles a real firm's scanner | **ASSUMED and weak.** The print-photograph round trip is the stronger half of week 6 for exactly this reason. |
| I | Five practitioners can be reached in September | **ASSUMED.** H-004 (Reddit OAuth, the only recorded route to a live practitioner voice) is open and founder-blocked. |
| J | Transcription checking needs no legal qualification | **REASONED.** Comparing our extraction to a page is not legal judgement. Promotion past `DEFECT_FLAGGED_PRODUCTION_LIMITED` is, and is gated on H-001. |
| K2 | The in-flight `limbs_not_decided` and POST changes land green in week 1 | **ASSUMED.** 4 + 1 checks failing at the time of writing. If they slip, week 1 becomes finishing them and every week shifts. |
| K | A ₹500/month extraction sub-cap is the right split of ₹3,500 | **ARBITRARY**, chosen to leave headroom for an answer step that is not being built. Revisit when it is. |
| L | Every Manupatra figure | **UNVERIFIED.** §9.1. |
| M | NJDG figures | **BETTER SOURCED, NOT VERIFIED HERE**, and measuring court backlog rather than software demand. §9.2. |

---

## 13. One-paragraph summary

Over September and October 2026 this project roughly doubles its obligation register on ground that
needs no delegated legislation — the AGM chain (s.96 all limbs, s.137 AOC-4, s.92(4) annual return),
then s.177 audit committee and vigil mechanism against the one rule instrument we hold — reads that
instrument for the first time and admits it only under a restriction code saying it is the 2014
as-made text, builds the extraction harness and step log that any future model work needs, makes the
first real model call in the project's history at haiku tier in shadow for about ₹11, decides in
writing whether OCR kills the extractor, produces the first false-negative measurement the project
has ever had against 15 seeded-defect documents, and publishes a page that makes process claims and
no accuracy claim. Total planned model spend is under ₹30 against a ₹7,000 two-month allowance,
which is the finding rather than the frugality: nothing on the critical path is gated on model
spend. It is gated on two human actions — a lawyer reading the register (H-001) and a person
downloading one gazette file (S-002, fifteen minutes, blocked since 21 August) — and on one
measurement nobody has taken. On 31 October, one of the nine preconditions for an accuracy claim
will be met, one partially, one unknown, and six not; the correct thing to say publicly will still
be what the system refuses to do.
