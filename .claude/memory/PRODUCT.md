# Product Definition

**Name:** placedon.com
**Tagline:** "Every HR team deserves an expert in the room."
**Live:** https://placedon-hr.vercel.app (free PoSH checker, prototype banner up)

## The golden rule
**LLM explains. Code decides. Lawyer verifies.**

`applicability.py` decides what the law requires. The LLM only translates a pre-verified packet
into English. Every number in the output is then checked verbatim against the source text,
programmatically. The safety property is enforced by code, not by model capability — which is why
model choice is a cost lever, not a correctness lever.

## Two tracks, two trust contracts
Compliance is the wedge that earns trust; operations is the work that earns daily use.

| | Compliance | Operations |
|---|---|---|
| Truth | The gazette | Curated published practice |
| Proof | Citation → PDF page | Provenance → source, date, sample size |
| Uncertain | **Abstain** | Draft anyway, flag assumptions, stay editable |
| Verified by | A human employment lawyer | Nobody |

**Leakage** — an operations answer wearing legal grammar — is the failure this introduces.
`trust-boundary-reviewer` exists solely to catch it. Full contract: `docs/05_HR_OPERATIONS_TRACK.md`.

## Scope
- **V1** — PoSH, Karnataka. Company Health Scan (free, no signup, ₹0 to run), cited Q&A with
  abstention, obligation calendar, document generation.
- **V1.5** — EPF, ESI, Karnataka S&E. Resume screener and CSV analysis *only* on an ephemeral
  design (they carry employee PII).
- **V2** — JD generator, offer letters, policies. Blocked on there being no confirmed Indian
  template source (`docs/06` §2).
- **V3** — ATS, call bot, integrations. Each needs a third party a solo founder can't unblock.

## What we know that most people don't
s.4 of the PoSH Act contains **no ten-employee threshold**. It says "every employer of a workplace
shall". The ten-worker figure is inferred from s.6(1). Every secondary source states it as though
s.4 contained it. This is both our best demo and the lawyer's first question.

## Constraints that bind everything
One founder, part-time, between classes. ₹3,500/month of API spend. No employee-level PII, ever.
Nothing reaches a user while `verified_by IS NULL`.
