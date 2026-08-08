# TODAY: 2026-08-09

## The one number moved

```
https://placedon-hr.vercel.app   →   200        LIVE
```

The free PoSH checker is public. Form, report, citations, abstention — all of it, working on a
phone. Four deploy bugs found and fixed getting there; see `.claude/loops/VERIFY_deploy.md`.

**Nobody has used it yet.** That is now a distribution problem, not a code problem.

## This week — three tracks, one is code

- [x] **A. Deploy — DONE.** https://placedon-hr.vercel.app · `GET /` 200 · `POST /check` 200 ·
      `POST /api/diagnose` 200 · `GET /api/generate/templates` 200. Verified in a browser at
      390×844, no overflow, no JS errors. The Next frontend (`/diagnose`, `/generate`) is a
      separate project and is **not** deployed — what is public is the server-rendered checker,
      which is the whole free journey and needs no JavaScript.
- [ ] **B. Lawyer.** `python3 scripts/review_pack.py` and `apply_verification.py --template`,
      then send both. 12 sections, one evening, ₹2,000–3,000. `docs/LAWYER_BRIEF.md` has the
      email. **Yours.**
- [ ] **C. Ten calls.** Two questions, in `docs/PLAN.md`. **Yours.** Log every one in
      `RESEARCH_LOG.md` under `[TRACK: market]`, including the bad ones.

## State

| | |
|---|---|
| `scripts/verify.py` | GO, 24 checks |
| Public URL | **https://placedon-hr.vercel.app** |
| Corpus | 30 PoSH sections, **0 verified** · 4 MCA provisions, secondary source |
| Documents live | `ic_order`, `posh_policy`, `board_report` |
| LLM spend, all time | ₹0.00 |
| Remote | private, pushed |

## Not this week

The 8 verticals, DPDP, EPF, the risk score, Stripe. All behind the same gate: verify one law,
talk to ten people. Reasons in `docs/PLAN.md`.

## Gate — 2026-09-05

Public URL · one lawyer sign-off · ten conversations · one person who says they would pay.
Miss the third and stop building until it happens.
