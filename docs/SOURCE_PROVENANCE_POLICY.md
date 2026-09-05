# Source provenance policy

Implemented and enforced in `checker/provenance.py`. This is not documentation of an intention;
`Claim(...)` raises at construction if the state is unsupportable.

## Evidence states

| State | Meaning | Servable to a user? |
|---|---|---|
| `VERIFIED` | Hashed local artifact + human review | Yes |
| `CORROBORATED` | A second **accessible** source agrees | Yes |
| `UNFETCHED_CORROBORATION` | An inaccessible source is *reported* to agree | No |
| `INFERRED` | Derived by this system, no external agreement | No |
| `UNRESOLVED` | Looked, found nothing conclusive | No |
| `RETRACTED` | Asserted, since disproved | No |

## What VERIFIED does and does not mean

`VERIFIED` means **verified against a named artifact**, not true in the abstract. The 17 MVP section
mappings are VERIFIED against `corpus/sources/companies_act_2013_indiacode.pdf`
(`d6e286d2…39af`). If that PDF is itself defective, the mapping is faithfully wrong. Single-source
verification is the current ceiling because the only independent source is blocked.

A claim should therefore always name its artifact. "s.173 is 49099" is not a claim; "s.173 is 49099
in INDIACODE_CA2013_PDF" is.

## The promotion rule

Nothing reaches `VERIFIED` without a source that is (a) present locally, (b) hash-matching, and
(c) human-reviewed. `can_promote()` refuses and states which condition failed.

An inaccessible URL supports `UNFETCHED_CORROBORATION` at most, **however authoritative the
publisher**. A source nobody could read is not evidence of its own contents. This is the rule that
keeps the India Code 403 from being quietly written up as verification.

A hash mismatch is treated as loss of verification, not as a warning: a source whose bytes changed
is not the source that was reviewed.

## Standing constraint

Blocked sources stay blocked. Do not bypass the MCA/India Code WAF, robots restrictions, or access
controls to raise an evidence state. If a source cannot be read within its terms, the honest record
is `BLOCKED` and a weaker state.

## Current sources

| ID | Accessibility | Role |
|---|---|---|
| `INDIACODE_CA2013_PDF` | ACCESSIBLE, hashed, reviewed | Basis of the section index |
| `INDIACODE_SECTION_VIEW` | BLOCKED (403, 2026-08-21) | Would confirm the index if readable |
