# Features

Status of what exists. `BACKLOG.md` holds the work items and blockers; this is the view of what
a user can actually do.

## Shipped and verified

| Feature | Entry point | Costs | Notes |
|---|---|---|---|
| Compliance Health Scan | `/diagnose` → `/result` | ₹0 | Deterministic. No model call. |
| District-scoped jurisdiction | `jurisdiction.py` | ₹0 | Refuses to fall back district → state |
| IC constitution order | `/generate/ic_order` | ₹0 | Validates s.4(2) **before** drafting |
| PoSH policy for display | `/generate/posh_policy` | ₹0 | s.19(b) |
| Board's Report PoSH extract | `/generate/board_report` | ₹0 | Rule 8(5)(x); abstains for Small Co / OPC |
| Lawyer review pack + return path | `scripts/review_pack.py`, `apply_verification.py` | ₹0 | 12 sections, derived from retrieval closure |
| Verification ratchet | `scripts/verify.py` | ₹0 | 19 checks, each bought by an incident |
| Agent index + search | `scripts/index_codebase.py`, `search_memory.py` | ₹0 | 0.05 ms mean |

## Built but unreachable

| Feature | Blocked by |
|---|---|
| Cited Q&A (`/ask`) | **0 of 30 sections verified.** Every packet abstains pre-flight. One lawyer-evening (H-2) opens all 12 core questions — rehearsed and proven. |

## Deliberately not built

| | Why |
|---|---|
| Offer letter, appointment letter | Operations track, no sourced corpus. The spec's CTC breakup (basic 50%, HRA 20%) is invented. BACKLOG O-1/O-2. |
| Complaint register | s.16 bars publishing complaint contents and identities; Rule 8(5)(x) only ever wanted integers. Counts in, contents never. |
| Risk score 0–100, HIGH/MEDIUM confidence | No derivation exists for either. Confidence is binary: answer or abstain. |
| Annual-return deadline for Bengaluru | Set per District Officer; we do not hold the notification. BACKLOG H-3. |

## Next, in order

1. **H-2** — lawyer, 12 sections, one evening. Unlocks the entire Q&A product.
2. **H-1** — ten customer conversations. Decides whether the buyer is HR or the CS/CA.
3. **T-8** — a git remote.
4. **H-4** — the Karnataka order of 4 Nov 2025.

Items 1 and 2 are human and cannot be built around. Everything else is waiting on them.
