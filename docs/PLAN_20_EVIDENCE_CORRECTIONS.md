# PLAN 20 — evidence corrections

Written 27-09-2026, hours after `PLAN_20_INHOUSE_CORPORATE.md`, against a commissioned
evidence review (`docs/research/IN_HOUSE_EVIDENCE_2026_09_27.md`, 423 lines, every claim
tagged `[A]` academic / `[G]` government / `[I]` industry-with-method / `[V]` vendor /
`[U]` unconfirmed).

**PLAN 20 is not withdrawn. Its product ranking survives intact and one of its riskiest
assumptions was independently confirmed.** But four of its claims are wrong or overstated,
one of its numbers was computed with a defect this same night's commit fixed, and its
central positioning sentence cannot be said in public as written.

The order below is by how much each correction changes what we do.

---

## 1. The moat is the corpus, not the idea. Say it that way.

PLAN 20 §1 says of as-of-date statutory research: **"Nobody sells the answer to that."**

That sentence is false, and it is false in the way that gets a founder cut apart in a
first meeting with a technical investor.

- **Akoma Ntoso is an OASIS standard** and natively tracks the temporal evolution of a
  legal text. Monica Palmirani (Bologna/CIRSFID) published the representation work from
  ~2005: *"Moving in the Time: An Ontology for Identifying Legal Resources"*, *"Temporal
  Dimensions in Rules Modelling"* (JURIX 2010), Temporal Defeasible Logic for
  modifications. OASIS LegalRuleML (ICAIL 2013) is the rules-side counterpart. `[A]`
- **legislation.gov.uk has shipped point-in-time revised legislation for over a decade** —
  per-provision version timelines, and explicit flagging of prospective versions not yet
  commenced. `[G]` **A government has shipped our differentiator, for another
  jurisdiction, since before this company existed.**
- **The recipe is published, three times over, in the last eighteen months:** French tax
  (arXiv:2608.09393), German statutes (arXiv:2605.23497), Brazilian constitution
  (arXiv:2506.07853). Date extraction from the fact pattern, version filtering,
  date-conditioned retrieval. `[A]` Anyone who reads arXiv can copy it in a quarter.

**What survives, and it is a stronger hand than PLAN 20 argued:**

| Measured | Value | Source |
|---|---|---|
| Static-corpus RAG retrieving the date-applicable version | **0% of the time** | arXiv:2608.09393 `[A]` |
| Static-corpus RAG strict accuracy | **2.7%** | same |
| Date-conditioned retrieval, same corpus | **98.3%** | same |
| Vanilla LLM *reasoning*-correctness on post-cutoff amendment questions | **0.00%** | arXiv:2605.23497 `[A]` |
| Web search bolted onto an LLM | **makes it worse** — marked recency bias on historically anchored tasks | same |
| Commercial legal systems exposing point-in-time retrieval as first-class | **none found** | arXiv:2606.09724 `[A]` |
| India Code | **no as-at-date view, and ~6 months stale** | Univ. of Melbourne library guide `[I]` |

So the problem is real, severe, measurable, and mechanically fixable with an effect size
of 2.7% → 98.3%. That is a very good slide. It is just not an *unclaimed* one.

**Rewrite the positioning as:** the concept is a twenty-year-old solved problem in
standards and a two-year-old solved problem in retrieval — *and nobody has built the Indian
bitemporal corpus, because India Code has no as-at-date view and runs six months stale.*
The moat is the corpus and the provenance chain that makes it admissible. Corpora are
slow, dull and expensive to copy. Ideas are not.

---

## 2. "Indian corporate law changes constantly" is false of the Act, and that changes our ingestion order

- **The Companies Act 2013 has ~4 amendment Acts in 13 years** (2015, 2017, 2019, 2020,
  plus the 2018 Ordinance and two in 2019). `[G]`/`[I]` If the pitch is "the Act changes
  constantly," the primary legislation contradicts the pitch.
- **The churn is in rules, forms and adjacent regulators.** SEBI LODR alone: **~6
  amendments during 2025** (1 May, 8 Sep, 27 Oct, 19 Nov, 16 Dec) and **≥2 in the first
  seven months of 2026**. `[G]`/`[I]` Subject matter: board composition, director
  appointments, related-party transactions, secretarial audit — **exactly our surface.**
- **February 2023 alone: 12 MCA notifications** amending rules, with form substitutions
  and omissions. `[I]`
- **A structural change with retroactive effect on process advice:** from 10-02-2026 RoCs
  became adjudicating officers under s.454, and Regional Directorates went 7 → 10
  effective 16-02-2026. `[I]` Any prior advice on where a penalty gets adjudicated is now
  wrong — and note that this is a change no amount of Act-text versioning would catch.

**Consequence for the build:** the recall register's value is driven by **rules and
adjacent regulators**, not by the Act. A bitemporal corpus of the Act alone would be
technically impressive and commercially close to inert. PLAN 20 §3 ranks the vault first
and change-alerts fourth; the *content* those alerts watch must be SEBI LODR and the
Companies Rules before it is the Act. `checker/scope.py` already declares nine bodies and
holds one — that shape is right, and the held one is the least eventful of them.

---

## 3. Do not sell penalty-avoidance. The penalties are smaller than the subscription.

- **Companies Act s.92(5) and s.137(3):** ₹10,000 plus ₹100/day, **capped at ₹2,00,000 for
  the company and ₹50,000 per officer.** `[G]` Lakhs, not crores.
- Our own proposed price band starts at ₹50,000/year. **At the top of the band the
  subscription costs more than the maximum penalty it avoids.**
- **Nobody has ever measured the cost of stale legal advice.** No study, survey, or
  insurance dataset. `[A]`-absent. Professional indemnity premiums of 1–3% of income are a
  premium, not a claims cost.
- The claim that MCA collected "₹10,000 crore in fines 2014–2023" traces only to
  **Grokipedia. It must not be used.**

**Consequence:** the value proposition is deal risk, indemnity exposure, and re-doing work
under time pressure — not statutory penalties. None of those three is published either,
which means they must come from customer interviews, and the interviews must ask for
rupees, not for agreement.

---

## 4. PLAN 20's own per-answer arithmetic used the defective number

PLAN 20 §5 computes the old price band's ceiling "at the measured ₹2.91 per answer." That
figure is the one this session's BUD-F2 commit fixed: it priced Sonnet 5 with Haiku 4.5's
token counts, **26.2% low**. PLAN 20 cites the 26.1% finding two paragraphs later and then
uses the uncorrected number anyway.

| | PLAN 20 as written | corrected |
|---|---|---|
| Cost per answer, DEFAULT_MODEL | ₹2.91 | **₹3.95** |
| Answers/month at ₹250 | ~86 | **~63** |
| Document checks/month, cached | ~26 | **~19** |
| Document checks/month, uncached | ~13 | **~10** |

The conclusion is unchanged and in fact strengthened: ₹3,000–6,000/year is not a floor for
this customer, it is below the floor. But the arithmetic in §5 must be restated.

---

## 5. The price band is defensible at the bottom and probably too low at the top

PLAN 20 proposes ₹50,000–5,00,000/year. Triangulation, **every input `[U]`**:

| Anchor | Per seat / year |
|---|---|
| Substitute they already buy (Manupatra) | ₹18,000 |
| Foreign tool actually being bought in India | ~₹1,40,000 |
| Legora (global, 10-seat min) | ~₹2,60,000 |
| Harvey base, *reported* only | ~₹12,60,000 |

A 5-seat team at the ₹1.4 lakh anchor is **~₹7,00,000/year** — above PLAN 20's ceiling.

Two warnings that matter more than the band:
- **Both India-specific price points come from one anonymous lawyer in one newspaper
  article.** Treat as a hypothesis to test, never as a fact in a deck.
- **Of 20 legal-AI vendors, 6 publish any price and 14 publish none** — Harvey, Legora,
  CoCounsel, Spellbook, Luminance and nine others publish nothing. `[V]` Anyone quoting a
  competitor's list price is quoting a rumour, and that includes us.

**And the sobering number an investor will find anyway:** the entire Indian legal-**AI**
market is modelled at **US$29.5M for 2024 (~₹250 crore)**, `[U]`, top-down. The three
market-size figures in circulation ($29.5M legal AI, $1.28bn legaltech, $800M cumulative
funding across 954 companies) are **mutually incoherent**; at least two are models, not
measurements. Lead with the pessimistic one and we own the room; get caught with the
optimistic one and we lose it.

---

## 6. Confirmed, and it validates the riskiest thing in PLAN 20

**MCA is not programmatically reachable.** The review's environment got **HTTP 403 from
mca.gov.in on every single request** (Akamai edge block — capital-ranges page, Monthly
Information Bulletin, DMS document endpoints); `mcacdm.nic.in` did not resolve;
`data.gov.in`'s API returned 503.

PLAN 20 §3 ranks the **vault** first precisely because MCA21 has no OAuth, no API and no
delegation, so customer-in-the-loop upload is the only lawful route to a client's own
documents. **That reasoning is now independently confirmed from outside this repo.** It is
the single most load-bearing assumption in the plan and it held.

---

## 7. Two claims to stop making, because the best evidence is against us

**AI does not beat lawyers at contract review.** ContractEval: best-in-class **F1 =
0.644**, near-zero on nuanced clause categories. VLAIR redlining: **human lawyer 79.7% vs
best AI tool 65.0%** — and redlining is the one task where the lawyer beat every tool.
VLAIR also let vendors **withdraw from individual tasks before publication**, and several
did, so even those scores are best-foot-forward. `[A]`/`[I]` PLAN 20 ranks NDA review 7th,
which is the right rank; the claim attached to it must be modest.

**The automation-bias argument for abstention is not supported.** The best-powered
peer-reviewed study (Alon-Barkat & Busuioc, N=605 and N=904, JPART) found **no automation
bias** — adherence to algorithmic advice was not greater than to equivalent human-expert
advice. `[A]` No study measures whether a practising lawyer accepts a wrong AI answer.

What **is** supported, at N=2,784: over-reliance rises with the **effort cost of
verification.** `[A]` That is a real finding and it argues for something we are already
building — the grey abstain state, the evidence pack, one-click provenance — but the
justification is *"make verification cheap,"* not *"lawyers are credulous about
machines."* Use the supported argument.

---

## 8. The gap to close, and it is two weeks of work

> **We can prove the differentiator works. We cannot yet prove it is worth paying for.**

Closing it needs original research, not more searching. The review names the exact
unclaimed number:

- The French CGI averages **5.69 historical versions per article**, one article at **94
  versions**. `[A]`
- **No Gazette-derived count of Companies Act / Companies Rules amendments per year exists
  — published by anyone, including MCA.** Nobody has counted **amendments that invalidate
  prior advice**, as opposed to "updates."
- TeamLease RegTech's widely-quoted **12,973 compliance updates in 2025** is a **vendor**
  figure spanning all seven compliance categories across central, state and local layers —
  **not corporate law** — and an "update" is not a change that invalidates advice. `[V]`
  They sell compliance software and profit from the number being large.

**So: count it.** Per-provision version counts for the Companies Act 2013 and its rules,
Gazette-derived, with an explicit coding rule separating *amendments that invalidate prior
advice* from cosmetic ones. It is countable, the corpus is already ingested (527 sections,
hash-stamped), `checker/amendment.py` and `checker/as_of.py` already parse the footnotes,
and `checker/observation_store.py` is already append-only bitemporal.

**It would be the first defensible number in this space, and it is ours to publish.** That
is worth more than a pitch deck: it converts our moat from an assertion into a
measurement, and it is the one asset on this list that a competitor reading arXiv cannot
copy in a quarter.

---

## 9. What changes in PLAN 20

| PLAN 20 | Action |
|---|---|
| §1 "Nobody sells the answer to that" | **Rewrite.** Concept is standardised and shipped elsewhere; moat is the Indian corpus + provenance. Keep the Vaquill and 31.7% HCER points — both stand. |
| §1 framing | Keep "Palantir for lawyers." Provenance-over-analysis is exactly what the bitemporal + admission-gate architecture is. |
| §3 ranking (vault first) | **Keep, unchanged.** Independently confirmed (§6 above). |
| §3 alert content | **Amend:** watch SEBI LODR and the Companies Rules before the Act. The Act barely moves. |
| §5 arithmetic | **Restate** at ₹3.95/answer. Consider raising the ceiling above ₹5,00,000. |
| §2 no-fine-tuning | **Keep.** Nothing in the evidence disturbs it; "weights cannot be as-of-dated" is unaffected. |
| new | Add the Gazette amendment-density count as a first-class deliverable, not a research nicety. |
| §preamble path | **Fix.** It cites `docs/BUSINESS_PLAN.md`, which is not in this repo — the file is `Placedon-law-business-plan/docs/BUSINESS_PLAN.md`, in the **public** repo that must never be edited from here. PLAN 20 says it "must be rewritten" while pointing at a local path that does not exist. Any rewrite is a draft handed to the founder, never a commit. |

---

## 10. Provenance of this document

Single commissioned review, one researcher, desk research only, 27-09-2026. Two threads it
could not close, for stated reasons rather than absence of evidence: official NSE/BSE
listed-company counts, and the conflict-of-interest disclosure in the second drafting RCT.
Both are single lookups and neither is load-bearing above.

It is **not** an independent replication, and every `[U]` above is exactly as weak as it is
labelled. The review's own closing section, *"What the numbers do not support,"* lists
fifteen claims we might reasonably want to make and cannot — including, at item 1, that
there is any published census of how many Indian companies have an in-house legal team.
**There is not.** Its ~45,000 estimate is the researcher's own extrapolation from a 2015
authorised-capital distribution and is labelled as such. Do not put it in a deck.
