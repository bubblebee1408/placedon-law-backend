# PLAN — finish the job: case-law search live, login, durable hosting

**Goal (what "done" means):** a user opens the app, types *"find the Tata–Mistry case"* and
gets the judgment (openable, labelled supporting-not-verified); signs in with email+password;
and it all runs on hosting, not a laptop tunnel.

## Hard constraints (these cap parallelism — not negotiable)
1. **One backend gate.** `scripts/run_tests.sh` binds `:8021`, cannot run concurrently, and the
   pre-commit hook runs it on **every** backend commit. → *All* backend commits serialize.
   There is no real backend parallelism, however many agents exist.
2. **Frontend is a separate repo + gate** (pnpm). → Frontend runs **in parallel** with backend.
3. **Hosting + deploy need the owner's cloud account.** An agent can prepare config; it cannot
   provision, pay, or connect a private repo. That step is human-gated.
4. Shared git worktrees + stash across sessions → stage explicit paths, never `git add -A`.

## Done so far (branch `claude/general-research`, local, GREEN)
- Step 1 `a07ae40` — judgment search engine. Step 1b `2c78b66` — real SC index (8,977 judgments
  2015–2026) + stopword matching. Step 2 — `sources.search` returns `judgments` (LICENSED
  discovery; verified "Tata Sons Cyrus Mistry" → the 2021 Tata/Cyrus judgment). (step-2 commit in gate.)
- Accounts: frontend PR #22 done; backend `claude/accounts` has only the STEP-0 decision record.

## The two lanes (the agentic system)
- **Lane B — backend (serialized, single writer; driven in a /loop):**
  - GR **step 3**: a conservative query router + `research.cases` verb (statute→`ask`/HELD;
    party/case query→judgments/LICENSED); `roles.REQUIRED` entry; CLI/REST parity. Gate GREEN.
  - Accounts backend: STEP 1–5 of `DECISION_ACCOUNTS.md` (migration 026, `auth.login`/sessions/
    invites/users, middleware, bootstrap). Gate GREEN.
  - Hosting config: `render.yaml` + prod ASGI entry + env manifest + runbook. (Commits serialize.)
- **Lane F — frontend (parallel, pnpm gate):**
  - GR **step 4**: a case-law surface rendering `judgments` from `sources.search` (the step-2
    contract already exists), each openable, labelled **supporting authority — not verified**.
    Server-only gateway, `EngineResult` never-as-abstention, console B/W tokens (AGENTS.md).
  - → **Delegated to a frontend agent now** (it builds against the step-2 fixture contract, so
    it needs no live backend).
- **Human gate (owner):** Render account + managed Postgres + Azure creds → deploy; final merges.

## Fastest path to "you can click find-a-Tata-case" (demo, no merge/hosting)
1. GR step 3 (Lane B) + GR step 4 (Lane F) land.
2. Point the local `:8000` gateway at this branch (`be-genresearch`) and the frontend at it.
3. → clickable end-to-end, on the existing http2 tunnel.

## Full completion order
step 3 → step 4 → run locally (demo) → merge GR → accounts backend → merge accounts →
hosting config → **owner provisions** → deploy gateway → re-point frontend → retire tunnel.

## Acceptance
- "find a Tata case" in the app → the 2021 Tata/Cyrus judgment, openable, LICENSED/supporting,
  never VERIFIED, never an obligation (scope.py). Backend gate GREEN; frontend gate green.
- Login works (passcode now; email/password when accounts ships).
- Live site reachable without the laptop (hosting) — the durable milestone.

## Why not a big agent swarm
The backend single-gate (constraint 1) makes >1 concurrent backend writer counterproductive
(gate collisions, shared-stash hazards). So the system is **2 lanes**: one backend worker (loop)
+ one frontend agent, with hosting human-gated. That is the honest maximum concurrency here.
