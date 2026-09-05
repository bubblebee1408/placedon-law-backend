# MVP Sections

Twelve core sections, chosen because applicability turns on facts that appear **in the document
itself** — which is what makes them checkable.

| § | Title | Why it is in the MVP | Applies to |
|---|---|---|---|
| 96 | Annual general meeting | AGM identification, timing | AGM_NOTICE |
| 101 | Notice of meeting | Notice period, recipients, content, shorter notice | AGM_NOTICE, BOARD_NOTICE |
| 102 | Statement annexed to notice | Explanatory statement for special business, interest disclosure | AGM_NOTICE |
| 103 | Quorum for meetings | Member-meeting quorum by company type | SHAREHOLDER_RESOLUTION |
| 114 | Ordinary and special resolutions | Classify the resolution; is the threshold identified | Both resolution types |
| 117 | Resolutions to be filed | Does this resolution trigger a filing | BOARD_RESOLUTION, SHAREHOLDER_RESOLUTION |
| 173 | Meetings of Board | Frequency, gap, notice framework | BOARD_NOTICE, BOARD_RESOLUTION |
| 174 | Quorum for Board meetings | Attendance, interested-director effect | BOARD_RESOLUTION |
| 175 | Resolution by circulation | Can this pass by circulation, or does it need a meeting | BOARD_RESOLUTION |
| 179 | Powers of the Board | Does the resolution describe a board power; s.179(3) matters | BOARD_RESOLUTION |
| 184 | Disclosure of interest by director | Interest disclosure, participation restriction | BOARD_RESOLUTION |
| 188 | Related party transactions | Category, approval route, disclosure | BOARD_RESOLUTION, SHAREHOLDER_RESOLUTION |

## High-risk conditional extensions — after the 12 are measured

| § | Why it waits |
|---|---|
| 180 | Restrictions on Board powers. Must identify the **triggering transaction facts**, never just "s.180 applies" |
| 185 | Loans to directors. High-risk family — should usually emit `human_review_required` |
| 186 | Loans, guarantees, investments. Fact-sensitive; `POSSIBLY_APPLICABLE` when amounts or prior exposure are absent |
| 177 | Audit Committee. **Conditional on company class** — must not fire on every private company |
| 178 | NRC / Stakeholders Committee. Same conditionality |

## Required output per section

```
section · rule_title · document_type · triggering_facts · applicability_status ·
legal_source · effective_date · reason · missing_facts · confidence · human_review_required
```

## Worked example — a resolution approving a transaction with a director-connected entity

```
Section 184
  Status        POSSIBLY_APPLICABLE
  Reason        The document identifies a director-connected counterparty.
  Missing facts Nature of the director's interest; disclosure timing.
  Action        Human review required.

Section 188
  Status        POSSIBLY_APPLICABLE
  Reason        The document appears to approve a transaction with a related party.
  Missing facts Transaction category, value, ordinary-course status, arm's-length status,
                company classification.
  Action        Check applicable rules and approval threshold.
```

The system must not output "compliant" because the resolution contains approval language.

## Construction rule — binding

**Do not implement any rule from memory.** For every section:
1. retrieve the official source
2. retrieve the relevant subordinate rules
3. record publication and effective dates **separately**
4. record amendments
5. create positive, negative, historical-date and insufficient-facts fixtures
6. create independently reviewed expected labels
7. add explicit false-positive and false-negative tests
