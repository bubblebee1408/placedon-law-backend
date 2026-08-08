# Verify: production deploy (Track A)

2026-08-09

## Verdict: **GO** — https://placedon-hr.vercel.app is live

| Route | Status |
|---|---|
| `GET /` — the checker form | **200** |
| `POST /check` — server-rendered report | **200** |
| `POST /api/diagnose` — JSON | **200** |
| `GET /api/generate/templates` | **200** |

Driven end to end in Chromium at a 390×844 phone viewport: form submits, report renders, cites
s.4(1), abstains on the deadline, **no horizontal overflow, no JS errors**.

## Four bugs, none of which any local test could see

**1. `jinja2` was never in `requirements.txt`.** `checker/app.py` imports it. Installed locally,
so 22 checks passed, `setup.sh` said "deps present", and the browser E2E ran green. The first
production deploy returned **500 on every route**. A dependency that exists only on the author's
laptop is an outage.

**2. The wrapper stripped the path it had just restored.** `api/index.py` reads the real path
from `__p`, then ran a mount-prefix fallback *unconditionally* — so `__p=/api/diagnose` was
restored and immediately reduced to `/diagnose`, which is not a route. Every JSON endpoint 404'd
while `GET /` and `POST /check` worked, because those have no `/api` prefix to lose.

**3. `/api` is a mount point AND a route prefix.** Narrowing the fallback to `/api/index` fixed
the JSON endpoints and broke the root. Both halves were the same confusion. Resolved by treating
`/api` and `/api/index` as *exact* mount points and never stripping `/api` as a prefix.

**4. Vercel chains rewrite rules.** `GET /` still 404'd. Two guesses were wrong, so I logged the
live ASGI scope instead of guessing a third time:

```
raw_path='/api/index'   raw_qs='__p=%2Fapi%2Findex'   __p='/api/index'
```

`vercel.json` had a bare `/` rule *and* a `/(.*)` rule. A request for `/` matched the first,
became `/api/index?__p=/`, and was then matched by the second **again** — arriving with `__p` set
to the function's own mount point. `/(.*)` already covers `/` with an empty capture, so the first
rule was redundant as well as harmful. Removed, and the wrapper now normalises a mount-point
`__p` to `/` so a future rewrite change cannot resurrect it.

## What the ratchet gained

Two checks, 22 → 24:

- **every third-party import in shipped code is pinned** — walks the AST of every shipped `.py`,
  excludes `scripts/` as tooling, treats starlette and pydantic as satisfied by fastapi. Proven
  by deleting the jinja2 line and watching it fail.
- **the Vercel wrapper routes every API path** — drives eight ASGI scopes including the chained
  rewrite that production found and local testing had not.

## The lesson

Three of these four were invisible to every form of local testing, because **local uvicorn serves
`checker.app` directly and never touches the wrapper**. The deploy path had no coverage at all
until it broke in public. Logging the live scope resolved in one deploy what two rounds of
reasoning had not.

## Still not deployed

The **Next.js frontend** — `/diagnose`, `/result`, `/generate`, `/ask`. What is public is the
server-rendered Python checker, which is the complete free-checker journey and needs no
JavaScript. The Next app is a separate Vercel project and a separate decision.
