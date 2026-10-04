# Fixture review — 11 proposals

Candidate replacements for benchmark fixtures invalidated under the
fail-closed convention. **Nothing here has been applied and no gold label
has been changed.** Each row records what the original claimed, the premise
it rests on, every qualifier the provision carries, which the replacement
restores and which it still omits.

The recommendation is a reading of the accounting beneath it, not a decision.

| # | ID | Provision | Action | Qualifiers still missing | Near-duplicate |
|---|---|---|---|---|---|
| 1 | `v2-p101-qbind-0` | s.101(1) | **SEND BACK** | `delegated_rule` | — |
| 2 | `v2-p101-qbind-1` | s.101(1) | **SEND BACK** | `delegated_rule` | — |
| 3 | `v2-p103-qbind-0` | s.103(1) | **ACCEPT** | — | — |
| 4 | `v2-p103-qbind-1` | s.103(1) | **ACCEPT** | — | — |
| 5 | `v2-p103-qbind-2` | s.103(1) | **ACCEPT** | — | — |
| 6 | `v2-p103-qbind-3` | s.103(1) | **ACCEPT** | — | — |
| 7 | `v2-p173-qbind-0` | s.173(1) | **ACCEPT** | — | — |
| 8 | `v2-p173-qbind-1` | s.173(1) | **ACCEPT** | — | — |
| 9 | `v2-p173-qbind-2` | s.173(1) | **ACCEPT** | — | — |
| 10 | `v2-p174-qbind-0` | s.174(1) | **SEND BACK** | — | `v2-p174-qbind-1 (overlap 100%)` |
| 11 | `v2-p174-qbind-1` | s.174(1) | **SEND BACK** | — | `v2-p174-qbind-0 (overlap 100%)` |

---

## 1. `v2-p101-qbind-0` — s.101(1) — SEND BACK

**Supersedes** `v2-p101-bind-0`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 101 sets twenty-one days as the length of clear notice required to call a general meeting.

**Proposed replacement**

> Section 101 sets twenty-one days as the length of clear notice required to call a general meeting, subject to the statutory shorter-notice consent requirement.

**Supporting premise** — served text, verbatim, not repaired

> (1) A general meeting of a company may be called by giving not less than clear twenty-one days' notice either in writing or through electronic mode in such manner as maybe prescribed: 2 [Provided that a general meeting may be called after giving shorter notice than that specified in this sub-section if consent, in writing or by

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `proviso` | Provided that a general meeting may be called after giving shorter notice | **PRESERVED** | restored in the claim's own words ('subject to') |
| `delegated_rule` | in such manner as maybe prescribed | **MISSING** | not carried by the replacement |

**Source transcription warnings**

- s.101(1) reads 'in such manner as maybe prescribed'; apparent intent 'may be prescribed' [MATERIAL TO TOOLING — entail_qualifier's 'as may be prescribed' pattern cannot match this text, so the delegated-rule qualifier is present in law and invisible to the checker]

**Recommendation — SEND BACK.** the replacement still omits 1 qualifier(s) (delegated_rule); a claim that purports to state the rule must carry them

---

## 2. `v2-p101-qbind-1` — s.101(1) — SEND BACK

**Supersedes** `v2-p101-bind-1`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 101 sets ninety-five per cent as the proportion of members whose consent permits shorter notice for an annual general meeting.

**Proposed replacement**

> Where shorter notice is given for an annual general meeting, section 101 requires the consent of not less than ninety-five per cent of the members entitled to vote at that meeting.

**Supporting premise** — served text, verbatim, not repaired

> (1) A general meeting of a company may be called by giving not less than clear twenty-one days' notice either in writing or through electronic mode in such manner as maybe prescribed: 2 [Provided that a general meeting may be called after giving shorter notice than that specified in this sub-section if consent, in writing or by

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `proviso` | Provided that a general meeting may be called after giving shorter notice | **PRESERVED** | restored in the claim's own words ('shorter notice') |
| `delegated_rule` | in such manner as maybe prescribed | **MISSING** | not carried by the replacement |

**Source transcription warnings**

- s.101(1) reads 'in such manner as maybe prescribed'; apparent intent 'may be prescribed' [MATERIAL TO TOOLING — entail_qualifier's 'as may be prescribed' pattern cannot match this text, so the delegated-rule qualifier is present in law and invisible to the checker]

**Recommendation — SEND BACK.** the replacement still omits 1 qualifier(s) (delegated_rule); a claim that purports to state the rule must carry them

---

## 3. `v2-p103-qbind-0` — s.103(1) — ACCEPT

**Supersedes** `v2-p103-bind-0`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 103 sets five members as the quorum for a public company with not more than one thousand members.

**Proposed replacement**

> Unless the company's articles provide for a larger number, section 103 sets five members as the quorum for a public company with not more than one thousand members.

**Supporting premise** — served text, verbatim, not repaired

> Unless the articles of the company provide for a larger number,-- (a) in case of a public company,-- (i) five members personally present if the number of members as on the date of meeting is not more than one thousand; (ii) fifteen members personally present if the number of members as on the date of meeting is more than one thousand but up to five thousand; (iii) thirty members personally present if the number of members as on the date of the meeting exceeds five thousand; (b) in the case of a private company, two members personally present, shall be the quorum for a meeting of the company. (2) If the quorum is

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `articles_override` | Unless the articles of the company provide for a larger number | **PRESERVED** | restored in the claim's own words ('unless') |
| `threshold` | not more than one thousand | **PRESERVED** | the claim carries the statute's own words |
| `scope_limit` | in the case of a private company | **NOT_APPLICABLE** | governs private company only; this claim is about a public company |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 4. `v2-p103-qbind-1` — s.103(1) — ACCEPT

**Supersedes** `v2-p103-bind-1`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 103 sets fifteen members as the quorum for a public company with more than one thousand but up to five thousand members.

**Proposed replacement**

> Unless the company's articles provide for a larger number, section 103 sets fifteen members as the quorum for a public company with more than one thousand but up to five thousand members.

**Supporting premise** — served text, verbatim, not repaired

> Unless the articles of the company provide for a larger number,-- (a) in case of a public company,-- (i) five members personally present if the number of members as on the date of meeting is not more than one thousand; (ii) fifteen members personally present if the number of members as on the date of meeting is more than one thousand but up to five thousand; (iii) thirty members personally present if the number of members as on the date of the meeting exceeds five thousand; (b) in the case of a private company, two members personally present, shall be the quorum for a meeting of the company. (2) If the quorum is

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `articles_override` | Unless the articles of the company provide for a larger number | **PRESERVED** | restored in the claim's own words ('unless') |
| `threshold` | not more than one thousand | **PRESERVED** | restored in the claim's own words ('more than') |
| `scope_limit` | in the case of a private company | **NOT_APPLICABLE** | governs private company only; this claim is about a public company |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 5. `v2-p103-qbind-2` — s.103(1) — ACCEPT

**Supersedes** `v2-p103-bind-2`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 103 sets thirty members as the quorum for a public company with more than five thousand members.

**Proposed replacement**

> Unless the company's articles provide for a larger number, section 103 sets thirty members as the quorum for a public company with more than five thousand members.

**Supporting premise** — served text, verbatim, not repaired

> Unless the articles of the company provide for a larger number,-- (a) in case of a public company,-- (i) five members personally present if the number of members as on the date of meeting is not more than one thousand; (ii) fifteen members personally present if the number of members as on the date of meeting is more than one thousand but up to five thousand; (iii) thirty members personally present if the number of members as on the date of the meeting exceeds five thousand; (b) in the case of a private company, two members personally present, shall be the quorum for a meeting of the company. (2) If the quorum is

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `articles_override` | Unless the articles of the company provide for a larger number | **PRESERVED** | restored in the claim's own words ('unless') |
| `threshold` | not more than one thousand | **PRESERVED** | restored in the claim's own words ('more than') |
| `scope_limit` | in the case of a private company | **NOT_APPLICABLE** | governs private company only; this claim is about a public company |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 6. `v2-p103-qbind-3` — s.103(1) — ACCEPT

**Supersedes** `v2-p103-bind-3`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 103 sets two members as the quorum for a private company.

**Proposed replacement**

> Unless the company's articles provide for a larger number, section 103 sets two members as the quorum for a private company.

**Supporting premise** — served text, verbatim, not repaired

> Unless the articles of the company provide for a larger number,-- (a) in case of a public company,-- (i) five members personally present if the number of members as on the date of meeting is not more than one thousand; (ii) fifteen members personally present if the number of members as on the date of meeting is more than one thousand but up to five thousand; (iii) thirty members personally present if the number of members as on the date of the meeting exceeds five thousand; (b) in the case of a private company, two members personally present, shall be the quorum for a meeting of the company. (2) If the quorum is

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `articles_override` | Unless the articles of the company provide for a larger number | **PRESERVED** | restored in the claim's own words ('unless') |
| `threshold` | not more than one thousand | **NOT_APPLICABLE** | governs public company only; this claim is about a private company |
| `scope_limit` | in the case of a private company | **PRESERVED** | restored in the claim's own words ('private company') |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 7. `v2-p173-qbind-0` — s.173(1) — ACCEPT

**Supersedes** `v2-p173-bind-0`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 173 sets thirty days as the deadline for holding the first Board meeting after incorporation.

**Proposed replacement**

> Section 173 sets thirty days as the deadline for holding the first Board meeting after incorporation, subject to the Central Government's power to exempt prescribed classes of companies by notification.

**Supporting premise** — served text, verbatim, not repaired

> (1) Every company shall hold the first meeting of the Board of Directors within thirty days of the date of its incorporation and thereafter hold a minimum number of four meetings of its Board of Directors every year in such a manner that not more than one hundred and twenty days shall intervene between two consecutive meetings of the Board: Provided that the Central Government may, by notification, direct that the provisions o

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `government_exemption` | the Central Government may, by notification, direct | **PRESERVED** | restored in the claim's own words ('central government') |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 8. `v2-p173-qbind-1` — s.173(1) — ACCEPT

**Supersedes** `v2-p173-bind-1`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 173 sets four as the minimum number of Board meetings in a year.

**Proposed replacement**

> Section 173 sets four as the minimum number of Board meetings in a year, subject to the Central Government's power to exempt prescribed classes of companies by notification.

**Supporting premise** — served text, verbatim, not repaired

> (1) Every company shall hold the first meeting of the Board of Directors within thirty days of the date of its incorporation and thereafter hold a minimum number of four meetings of its Board of Directors every year in such a manner that not more than one hundred and twenty days shall intervene between two consecutive meetings of the Board: Provided that the Central Government may, by notification, direct that the provisions o

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `government_exemption` | the Central Government may, by notification, direct | **PRESERVED** | restored in the claim's own words ('central government') |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 9. `v2-p173-qbind-2` — s.173(1) — ACCEPT

**Supersedes** `v2-p173-bind-2`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 173 sets one hundred and twenty days as the maximum gap between two consecutive Board meetings.

**Proposed replacement**

> Section 173 sets one hundred and twenty days as the maximum gap between two consecutive Board meetings, subject to the Central Government's power to exempt prescribed classes of companies by notification.

**Supporting premise** — served text, verbatim, not repaired

> (1) Every company shall hold the first meeting of the Board of Directors within thirty days of the date of its incorporation and thereafter hold a minimum number of four meetings of its Board of Directors every year in such a manner that not more than one hundred and twenty days shall intervene between two consecutive meetings of the Board: Provided that the Central Government may, by notification, direct that the provisions o

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `government_exemption` | the Central Government may, by notification, direct | **PRESERVED** | restored in the claim's own words ('central government') |

**Recommendation — ACCEPT.** restores every qualifier the provision attaches to this rule, on a complete premise from a clean source span

---

## 10. `v2-p174-qbind-0` — s.174(1) — SEND BACK

**Supersedes** `v2-p174-bind-0`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 174 sets one-third as the fraction of total strength forming the quorum for a Board meeting.

**Proposed replacement**

> Section 174 sets the quorum for a meeting of the Board at one-third of the total strength or two directors, whichever is higher.

**Supporting premise** — served text, verbatim, not repaired

> (1) The quorum for a meeting of the Board of Directors of a company hall be one-third of its total strength or two directors, whichever is higher, and the participation of the directors by video conferencing or by other audio visual means shall also be counted for the purposes of quorum under this s

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `selector` | whichever is higher | **PRESERVED** | the claim carries the statute's own words |

**Near-duplicate of** v2-p174-qbind-1 (overlap 100%).

**Source transcription warnings**

- s.174(1) reads 'of a company hall be one-third'; apparent intent 'shall be' [cosmetic — does not change legal effect]

**Recommendation — SEND BACK.** asserts substantially the same proposition as v2-p174-qbind-1 (overlap 100%); two fixtures carrying one item's worth of signal, and one should be replaced with a genuine negative

---

## 11. `v2-p174-qbind-1` — s.174(1) — SEND BACK

**Supersedes** `v2-p174-bind-1`  
**Defect** stated a real quantity-to-obligation binding unconditionally where the provision qualifies it

**Original claim**

> Section 174 sets two directors as the floor for the quorum for a Board meeting.

**Proposed replacement**

> Section 174 sets the quorum for a meeting of the Board at two directors or one-third of the total strength, whichever is higher.

**Supporting premise** — served text, verbatim, not repaired

> (1) The quorum for a meeting of the Board of Directors of a company hall be one-third of its total strength or two directors, whichever is higher, and the participation of the directors by video conferencing or by other audio visual means shall also be counted for the purposes of quorum under this s

**Qualifier accounting**

| kind | trigger in source | status | note |
|---|---|---|---|
| `selector` | whichever is higher | **PRESERVED** | the claim carries the statute's own words |

**Near-duplicate of** v2-p174-qbind-0 (overlap 100%).

**Source transcription warnings**

- s.174(1) reads 'of a company hall be one-third'; apparent intent 'shall be' [cosmetic — does not change legal effect]

**Recommendation — SEND BACK.** asserts substantially the same proposition as v2-p174-qbind-0 (overlap 100%); two fixtures carrying one item's worth of signal, and one should be replaced with a genuine negative
