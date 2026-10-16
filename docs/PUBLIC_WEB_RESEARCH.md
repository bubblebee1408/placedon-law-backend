# Public web research

`research.web` is an authenticated, read-only gateway verb for public web discovery. It is
separate from held-law retrieval, Vault search, verified legal answers, and official docket
services. It calls Exa's Answer API only after query-specific user consent.

## Enablement

Keep the feature disabled until the workspace has approved Exa's terms, query data egress,
retention, and billing. Configure these only in the backend's secret environment; never put
the API key in frontend variables or source control:

```text
PLACEDON_EXA_WEB_ENABLED=1
EXA_API_KEY=<server-side secret>
```

The default `.env.example` leaves the feature disabled and the key empty. After adding the
secret, restart the gateway and verify its provider setup through a controlled test workspace.

## Request and trust boundary

The request accepts only `query`, `mode` (`GENERAL_WEB` or `CASE_DISCOVERY`) and
`external_search_consent`. It accepts no matter ID, document, Vault text, conversation ID,
or history. The frontend binds consent to the exact text: editing the question clears the
checkbox, and the Search button remains disabled until the user consents again.

The gateway caps queries at 800 characters, rejects calls without consent, uses an 18-second
timeout, limits response size to 1 MB, keeps at most eight HTTPS citations, rejects redirects,
and caps in-flight provider calls at four per gateway process. Provider errors are returned as
typed, sanitized outcomes. The concurrency cap is process-local; production deployments with
multiple workers should add a shared per-workspace rate limit before enabling broad access.

## Docket and legal boundaries

Queries asking for a current case status, latest order, recent/next hearing, listing, or case
update are stopped before Exa. Ambiguous requests ask for court and case identifiers; specific
requests link to official Supreme Court and eCourts portals. This prototype does not retrieve a
live docket. Case discovery can return public judgments and reporting as candidate sources,
clearly labeled as public-web research, never as held or verified law.

## Verification

Run the provider tests without a network call:

```bash
python3 checker/public_web.py --test
PYTHONPATH=. python3 gateway/verbs.py
PYTHONPATH=. python3 gateway/roles.py --test
```

The feature returns `NOT_CONFIGURED` until both server settings are present. That is an
intentional status, not a successful live-search result.
