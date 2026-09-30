"""The gateway: auth, tenancy, audit, and the HTTP surface (PLAN_18 §2.1).

Ring 3. It may import from the engine; nothing in the engine may import from here. The
legal core stays reachable without any of this: `checker/api.py` remains pure and
stdlib-only, and `scripts/serve_api.py` still serves it over the stdlib HTTP server. The
gateway mounts that same `checker.api.handle` in-process rather than reimplementing it, so
there is exactly one router and `/v1` cannot drift between the two ways of reaching it.
"""
