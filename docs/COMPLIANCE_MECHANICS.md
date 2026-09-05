# Compliance mechanics — engine reference

Derived from a full harvest of India Code's holdings for the Companies Act 2013
(1,183 items: 527 sections, 345 rules, 153 notifications, 124 circulars, 26
orders, 7 schedules), reading Gazette text from the DSpace bitstream API.

Everything here is a **rule for the engine**, not advice. Each entry names its
provision. Unresolved points are listed in §4 and must not be hard-coded.

## 1. The distinction the engine is built around

An obligation's deadline is either computable from incorporation and
financial-year close, or it depends on a date the company chooses. These require
different machinery, and conflating them produces confident wrong dates.

### Statute-fixed — computable in advance

| Obligation | Formula | Provision |
|---|---|---|
| First Board meeting | `incorporation + 30 days` | s.173(1) |
| First auditor (non-Govt) | `registration + 30 days` | s.139(6) |
| First AGM | `first_FY_close + 9 months` | s.96(1) 1st proviso |
| AGM outer limit | `FY_close + 6 months` | s.96(1) 1st proviso |
| **OPC financial statements** | `FY_close + 180 days` | s.137(1) 3rd proviso |
| Dormant return MSC-3 | `FY_end + 30 days` | r.7 Cos (Misc) Rules 2014 |
| AOC-4 where no AGM held | `AGM_due + 30 days` | s.137(2) |
| MGT-7 where no AGM held | `AGM_due + 60 days` | s.92(4) |

### Company-chosen — not computable; the event date is an input

| Obligation | Formula | Provision |
|---|---|---|
| MGT-7 / MGT-7A | `actual_AGM + 60 days` | s.92(4) |
| AOC-4 | `actual_AGM + 30 days` | s.137(1) |
| AOC-4 (adjourned adoption) | `adjourned_AGM + 30 days` | s.137(1) 2nd proviso |
| ADT-1 | `appointment_meeting + 15 days` | s.139(1); r.4(2) |
| Board-meeting gap | `last_meeting + 120 days` | s.173(1) |
| s.188(3) ratification | `contract_date + 3 months` | s.188(3) |
| MBP-1 | no date — event-triggered on a Board meeting | s.184(1); r.9 |
| Board's report | no date — precondition of the AGM | s.134(3), (6) |

### Hybrid — the only one

    subsequent AGM = MIN( FY_close + 6 months,            statute-fixed
                          previous_AGM + 15 months )      carried forward as state

`previous_AGM_date` must persist across years. A company that took a three-month
Registrar extension in year N will usually find the fifteen-month limb binds in
year N+1 before the six-month limb does.

## 2. Traps that produce confidently wrong answers

**s.173(5) is a FLOOR, not a ceiling.** OPC, small and dormant companies need one
Board meeting per half calendar year with a gap of **not less than** ninety days.
An engine reusing the 120-day comparison operator reports compliance for meetings
held thirty days apart.

**Auditor ratification was abolished.** The first proviso to s.139(1) was omitted
by Act 1 of 2018 s.40 w.e.f. 7 May 2018. There is no annual ratification
obligation from FY 2018-19. Generating one is described in the source research as
the single most common false positive in Indian compliance calendars.

**s.173(1) says "every year" without defining it.** s.173(5) says "calendar
year". SS-1 treats s.173(1) as calendar. The Act does not say so — expose as a
policy switch, do not silently pick financial year.

**OPC 180 days is not six months.** 31 March + 180 days = 27 September; six
months = 30 September. Compute in days.

**para 2A gates every private-company exemption.** G.S.R. 583(E) inserted para 2A
into G.S.R. 464(E): the exemptions apply only to a private company that has not
defaulted in filing under s.92 or s.137. One late AOC-4 collapses the whole set —
signing relief, start-up board-meeting relaxation, interested-director
participation, related-party voting. Carry a per-company default flag and
re-evaluate every exemption against it.

**Small company: both limbs are conjunctive.** "or" was substituted by "and"
(S.O. 504(E), 13 Feb 2015). Both paid-up and turnover tests must be satisfied.
Turnover is tested against the **immediately preceding** financial year, so the
two limbs use different periods. A holding or subsidiary company is never small.
Status is re-tested every year; it is not sticky.

**A private subsidiary of a public company is a public company** for the whole
Act (s.2(71) proviso) — so not small, no MGT-7A, no abridged board report, and no
G.S.R. 464(E) exemptions.

**Rule 15(3) operators differ by clause.** Clause (a) items (i)-(iv) are `>=`
("ten per cent or more") since G.S.R. 309(E), 30 Mar 2017 — before that, `>`.
Clauses (b) and (c) remain strictly `>`. Do not apply one operator uniformly.

**Rule 15(3) rupee caps were removed mid-year.** G.S.R. 857(E), 18 Nov 2019.
FY 2019-20 is split: transactions before that date use the capped test, from that
date the uncapped. Date-stamp each transaction; do not batch by year.

**Rule 15(3) denominators are historical and audited.** Turnover and net worth
come from the **audited** financial statement of the **preceding** year. If those
are unaudited the rule supplies no denominator — return "cannot determine", never
substitute.

**Dormant status is ROC-conferred, not self-assessed.** Meeting the "inactive"
test is not enough; the engine must hold an MSC-2 certificate date.

## 3. Fine vs penalty — different remediation paths

Penalties (adjudicated by the Registrar under s.454): s.92(5), s.134(8),
s.137(3), s.173(4), s.184(4), s.188(5).

Fines (criminal, court-imposed, **not** decriminalised): s.99 (AGM default),
s.129(7) (financial statements), s.147 (auditors).

The engine must not present them identically.

## 4. Unresolved — do not hard-code

| # | Issue | What resolves it |
|---|---|---|
| 1 | Does the Registrar's AGM extension displace the 15-month limb, or only the 6-month one? | ROC order practice or MCA clarification. Conservative default: extend only the 6-month limb |
| 2 | OPC annual-return deadline — s.92(4) has no OPC limb and s.96 does not apply, so no "should have been held" date exists | MGT-7A instruction kit or an MCA circular. Contrast s.137, which does give the OPC an express 180-day rule |
| 3 | "Every year" in s.173(1) — calendar or financial? | SS-1 or MCA clarification |
| 4 | s.134(4) (single-item OPC report) vs Rule 8A (ten items) — primary vs subordinate | MCA clarification or judicial view; neither located |
| 5 | Rule 15(2) bars an interested director's *presence* for RPT discussions; G.S.R. 464(E) Sl.13 lets a private company's interested director *participate* | No resolving instrument. Surface both |
| 6 | Rule 15(3) aggregation — per related party or across all? | Not stated in the rule. Default to the stricter reading |
| 7 | Does s.129(3) still extend "subsidiary" to associate and JV after Act 1 of 2018 s.33? | Gazette text of that section. Until then flag associate-only structures for review |
| 8 | First-auditor ADT-1 — s.139(6) contains no notice obligation and r.4(2) is tied to s.139(1) | ADT-1 instruction kit or MCA circular. Advisory only |

## 5. Corroboration of SD-003

The harvest independently found an **unclosed amendment bracket in s.92's record**
(`<sup>4</sup>[` opened at sub-section (2) and never closed), matching the defect
class recorded in `docs/SOURCE_DEFECTS.md`. It is a genuine India Code markup
defect, and s.92 is not one of the ten we had already identified — so the
residual count is at least eleven, not ten.
