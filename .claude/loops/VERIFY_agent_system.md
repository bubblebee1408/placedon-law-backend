# Verify: agent system

Agent: code-reviewer, adversarial · 2026-08-08 · brief was *find checks that pass vacuously*

## Verdict: NO-GO on first pass → GO after four fixes

Three HIGH findings, each proven with a working bypass. The reviewer reintroduced the bug and
showed the named check still printed PASS.

## Confirmed and fixed

| Sev | Finding | Fix |
|---|---|---|
| HIGH | `_search_ranks_implementation` and `_index_excludes_itself` **asserted nothing** when `.claude/index.json` was absent — and it is gitignored, so absent on every fresh clone and in CI | `_index()` now **builds** the index if missing. Never skip a check because its input is missing. |
| HIGH | `_cors_expose` grepped the whole of `app.py` for `"X-Blocking-Issues"`, which also appears at the response-header site. Deleting it from `expose_headers` left the string present and the check green — the original incident, undetected | Reads `app.user_middleware` and inspects the real `CORSMiddleware` kwargs |
| HIGH | `_no_s4_threshold` never touched `checker/assess.py`, the **only** file that emits the citation. Flipping `CITE_THRESHOLD` → `CITE_S4` there passed | Runs `assess()` on an 8-worker profile and reads the citation actually emitted |
| MED | `_index_excludes_itself` combined a substring check with a **stale artifact** — deleting the `rel in SKIP_FILES` clause while leaving the definition passed | Rebuilds from current source and asserts on the result |
| LOW | `GENERATED` named `backend/.budget.json`; the real path is `corpus/.budget.json` | corrected |
| LOW | `setup.sh` carried a hand-kept dep list that omitted pinned `python-multipart` and named three unpinned packages | `scripts/check_deps.py` reads `requirements.txt` |

## Proof the fixes bite

Each bug reintroduced, one at a time:

```
remove X-Blocking-Issues from expose_headers only (string still present once elsewhere)
  FAIL  CORS exposes the headers the browser actually reads
        CORSMiddleware does not expose: ['x-blocking-issues']

flip citation=CITE_THRESHOLD -> CITE_S4 in assess.py
  FAIL  s.4 is never cited as the source of the ten-employee threshold
        cited to 's.4(1), PoSH Act 2013' — s.4 does not contain it; this is the original incident

delete .claude/index.json (fresh-clone state)
  PASS  agent search ranks the implementation above the documentation   (index rebuilt on demand)
```

## Cleared on inspection

BM25F maths — idf, the `[doc_id, body_tf, ident_tf]` stride, `df = len(flat)//3` — verified
against the live index across every term's postings, no anomalies. `index_codebase.py` SKIP
logic empirically correct. `setup.sh` idempotent across two consecutive runs; `set -euo
pipefail` propagates correctly through the `npm ci || npm install` fallback.

Five other checks (`_budget_derived`, `_form_state`, `_verification_honest`,
`_warning_placement`, `_tier1_derived`) survived constructed bypass attempts.

## The lesson

**String presence is not a proxy for behaviour**, and **a check that skips when its input is
missing is worse than no check** — it reports PASS for an incident it did not examine. Both
failure modes hid inside a file whose entire purpose is to be trusted.
