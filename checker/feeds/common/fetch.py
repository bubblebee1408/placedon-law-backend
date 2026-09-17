"""One HTTP path for every feed adapter, gated by checker.robots, streamed and capped.

## Ported shape, and why it grew past the JS original

`server/providers/common/http.js` (gods-eye-view, read via `gh api` 2026-09-17) caps a
streamed response body during the read: it checks Content-Length first, then reads
chunk-by-chunk and cancels the moment a running total crosses the cap, so a malicious
or merely oversized upstream can't OOM the proxy. `_read_capped()` below ports that
shape directly -- it is the one piece of `http.js` worth taking outright.

Everything past that is new, because two things were measured on 2026-09-17 against
the first real feed this module will serve (OFAC's Specially Designated Nationals
list) that gods-eye-view's sources never do:

1. **The entry URL is not the payload URL, and the payload URL expires.**
   `https://www.treasury.gov/ofac/downloads/sdn.xml` answers with HTTP 302 to a
   PRE-SIGNED AWS GovCloud S3 object
   (`wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/...?X-Amz-Expires=3600...`)
   that stops working in an hour. Caching or hard-coding that resolved URL would be
   keying evidence off an address guaranteed to go stale. So `fetch()` never treats
   the resolved URL as identity: the caller-supplied `entry_url` is what a
   `FetchResult` carries as `.url`, always -- see `checker/feeds/__init__.py`.

2. **The robots-governed host is not the payload host, and the payload host has none.**
   Measured the same day: `www.treasury.gov/robots.txt` -> 301 (nothing usable at that
   host); `ofac.treasury.gov/robots.txt` -> 200, a normal Drupal file;
   `sanctionslistservice.ofac.treas.gov` -> 404; the S3 payload host publishes no
   robots.txt at all. `checker.robots` fails closed by design (see its own
   docstring), and an unloaded ruleset denies everything -- so "check robots on
   whatever host the bytes end up coming from" would refuse this feed forever, and
   silently skipping the check to make it work would be exactly the source-policy
   bypass CLAUDE.md forbids. The resolution here is the same one this repository
   already reached for G.S.R. 700(E)-shaped problems: make the policy decision
   EXPLICIT rather than automatic. `fetch()` evaluates robots against the ENTRY
   host ONLY -- the host actually named in the URL a feed was configured with --
   and refuses to auto-follow any redirect urllib would otherwise chase silently.
   A redirect is followed exactly when the caller has named its target host in
   `allow_redirect_hosts`, and either way both hosts are recorded on the
   `FetchResult` (`.url` stays the entry URL; `.resolved_host` names the target
   when one was followed; `.note` says which). Robots is not re-evaluated against
   the redirect target: RFC 9309 binds a host to policy over its own paths, not
   over an address it happens to redirect a request to, and here the target
   publishes no file to evaluate in any case. If a caller does not name the
   redirect target as trusted, the fetch is refused and says so -- a recorded
   refusal, which is a correct terminal state (`checker/acquisition_log.py`'s
   HUMAN_RETRIEVAL_REQUIRED is exactly this kind of "stopped, not failed").

3. **Size.** The SDN payload measured 29,076,910 bytes on 2026-09-15. `fetch()`
   never buffers past `max_bytes` (default 64MB -- comfortably above the measured
   29MB, not a shrug): `_read_capped()` checks the declared Content-Length up
   front and aborts the read the instant the running total would exceed the cap,
   the same defence `http.js` uses. What this module does NOT do is stream
   straight to disk below that cap -- content still passes through memory once, as
   `bytes`, before `checker/feeds/common/cache.py` writes it. That is a real
   limit, stated in the final report, not hidden behind "streaming" language that
   would overclaim what a 64MB stdlib-only design actually does.

## Injection seams, so `_test()` never touches the network

`rules`: pass a `Rules` built with `checker.robots.parse()` (no network) instead of
letting `fetch()` call `checker.robots.fetch_rules()` (which does). `opener`: pass a
fake callable shaped like `_default_opener` in place of the real urllib-backed one.
Every test below supplies both.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from hashlib import sha256 as _sha256
from typing import Callable
from urllib.parse import urlsplit

from checker.feeds import EMPTY_SHA256, FetchResult
from checker.provenance import ACCESSIBLE, BLOCKED, NOT_FOUND, UNREACHABLE
from checker.robots import USER_AGENT, Rules, allowed, fetch_rules, ssl_context

# Measured 2026-09-15: OFAC SDN XML is 29,076,910 bytes. 64MB is headroom above the
# largest payload measured against this module, not an arbitrary round number.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
_READ_CHUNK = 1024 * 1024

_REDIRECT_CODES = (301, 302, 303, 307, 308)


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Turns an auto-followed redirect into a catchable HTTPError.

    Default urllib silently chases 3xx responses across hosts. Returning None from
    `redirect_request` makes urllib raise `HTTPError` with the redirect's own status
    and headers instead -- which is what lets `fetch()` SEE the hop (and the
    `Location` it points to) rather than discovering, after the fact, that bytes
    came from a host nobody ever asked robots.txt about.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 (urllib's name)
        return None


def _default_opener(url: str, *, timeout: float):
    """Real network path. Never exercised by `_test()` -- only `fetch()`'s
    production default. Verifies TLS the same way `checker.robots.Fetcher` does;
    an unverified source is worth less than no source (see robots.py)."""
    ctx = ssl_context()
    if ctx is None:
        raise RuntimeError("no CA bundle available; refusing an unverified TLS fetch")
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx), _RefuseRedirects())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return opener.open(req, timeout=timeout)


class _Truncated(Exception):
    """The server declared N bytes and delivered fewer. RT-04."""


def _read_capped(resp, max_bytes: int) -> tuple[bool, bytes]:
    """Read a response body up to `max_bytes`, cancelling the moment the running
    total would cross it. Ported from http.js's `readCappedResponseText` shape
    (STEP 1): check the declared length first, then police the actual bytes read,
    because a declared Content-Length is a claim, not a guarantee.
    Returns (too_large, content).
    """
    declared = resp.getheader("Content-Length") if hasattr(resp, "getheader") else None
    declared_n: int | None = None
    if declared is not None:
        try:
            declared_n = int(declared)
            if declared_n > max_bytes:
                return True, b""
        except ValueError:
            declared_n = None  # a malformed header proves nothing either way

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return True, b""
        chunks.append(chunk)

    # RT-04: a declared Content-Length the body does not reach means the connection
    # dropped mid-transfer. Until 2026-09-18 that short body was returned as a
    # complete, ACCESSIBLE fetch -- so half of the SDN list, or a truncated Gazette
    # page, would have been hashed, cached and parsed as if it were the whole
    # source. A partial document is not a smaller document; it is an unknown one.
    if declared_n is not None and total < declared_n:
        raise _Truncated(f"declared {declared_n} bytes, received {total}")
    return False, b"".join(chunks)


def _refused(source_id: str, entry_url: str, behaviour: str, *,
            http_status: int | None = None, note: str) -> FetchResult:
    return FetchResult(source_id=source_id, url=entry_url, sha256=EMPTY_SHA256, content=b"",
                       source_behaviour=behaviour, http_status=http_status, note=note)


def fetch(source_id: str, entry_url: str, *,
         rules: Rules | None = None,
         allow_redirect_hosts: tuple[str, ...] = (),
         opener: Callable[..., object] = _default_opener,
         max_bytes: int = DEFAULT_MAX_BYTES,
         timeout: float = 30.0) -> FetchResult:
    """Fetch `entry_url`, gated by checker.robots against ITS host, streamed and
    capped at `max_bytes`. Never auto-follows a redirect to a different host unless
    that host appears in `allow_redirect_hosts`; either way, `.url` on the result is
    always `entry_url`, never a resolved target. See this module's docstring for
    the measured OFAC case that shaped these choices.
    """
    origin = f"{urlsplit(entry_url).scheme}://{urlsplit(entry_url).netloc}"
    live_rules = rules if rules is not None else fetch_rules(origin)
    if not allowed(entry_url, live_rules):
        reason = "robots.txt disallows it" if live_rules.loaded else \
                 f"robots.txt not loaded ({live_rules.source})"
        return _refused(source_id, entry_url, BLOCKED, note=f"refused: {reason}")

    try:
        resp = opener(entry_url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return _handle_http_error(source_id, entry_url, exc, allow_redirect_hosts, opener,
                                  timeout, max_bytes)
    except (urllib.error.URLError, OSError) as exc:
        return _refused(source_id, entry_url, UNREACHABLE, note=f"unreachable: {exc}")

    return _finish(source_id, entry_url, resp, max_bytes)


def _handle_http_error(source_id: str, entry_url: str, exc: urllib.error.HTTPError,
                       allow_redirect_hosts: tuple[str, ...], opener, timeout: float,
                       max_bytes: int) -> FetchResult:
    if exc.code == 404:
        return _refused(source_id, entry_url, NOT_FOUND, http_status=404,
                        note="404: the entry host answered and said no such resource")

    if exc.code in _REDIRECT_CODES:
        location = exc.headers.get("Location", "") if exc.headers is not None else ""
        target_host = urlsplit(location).netloc if location else ""
        entry_host = urlsplit(entry_url).netloc

        if not target_host or target_host not in allow_redirect_hosts:
            return _refused(
                source_id, entry_url, BLOCKED, http_status=exc.code,
                note=(f"entry host {entry_host} redirected ({exc.code}) to "
                      f"{target_host or '(no Location header)'}, which is not in "
                      f"allow_redirect_hosts -- refused rather than followed silently"))

        # An explicitly-trusted redirect target: fetch it as its own request. The
        # entry URL, not this one, remains the FetchResult's identity.
        try:
            resp = opener(location, timeout=timeout)
        except urllib.error.HTTPError as exc2:
            return _refused(source_id, entry_url, BLOCKED, http_status=exc2.code,
                            note=f"entry redirected to trusted host {target_host}, "
                                 f"which then answered {exc2.code}")
        except (urllib.error.URLError, OSError) as exc2:
            return _refused(source_id, entry_url, UNREACHABLE,
                            note=f"entry redirected to trusted host {target_host}, then unreachable: {exc2}")
        return _finish(source_id, entry_url, resp, max_bytes,
                       resolved_host=target_host,
                       note=f"served via redirect: {entry_host} -> {target_host}")

    if 500 <= exc.code < 600:
        return _refused(source_id, entry_url, UNREACHABLE, http_status=exc.code,
                        note=f"{exc.code}: the entry host did not give a real answer")
    return _refused(source_id, entry_url, BLOCKED, http_status=exc.code,
                    note=f"{exc.code}: refused")


def _finish(source_id: str, entry_url: str, resp, max_bytes: int, *,
           resolved_host: str = "", note: str = "") -> FetchResult:
    try:
        too_large, content = _read_capped(resp, max_bytes)
    except _Truncated as exc:
        # UNREACHABLE, not BLOCKED: the host answered and then stopped talking.
        return _refused(source_id, entry_url, UNREACHABLE,
                        http_status=getattr(resp, "status", None),
                        note=f"truncated transfer ({exc}) -- refused rather than "
                             "treated as a complete document")
    status = getattr(resp, "status", None)
    if too_large:
        return _refused(source_id, entry_url, BLOCKED, http_status=status,
                        note=f"body exceeds {max_bytes} bytes ({note + '; ' if note else ''}"
                             f"refused to buffer it rather than truncate it silently)")
    return FetchResult(source_id=source_id, url=entry_url, sha256=_sha256(content).hexdigest(),
                       content=content, source_behaviour=ACCESSIBLE, http_status=status,
                       resolved_host=resolved_host, note=note)


# ── offline test doubles ─────────────────────────────────────────────────────

class _FakeResponse:
    """Shaped like http.client.HTTPResponse for the parts fetch.py touches."""

    def __init__(self, status: int, body: bytes, *, headers: dict | None = None):
        self.status = status
        self._body = body
        self._pos = 0
        self._headers = headers or {}

    def getheader(self, name: str):
        return self._headers.get(name)

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            chunk, self._pos = self._body[self._pos:], len(self._body)
            return chunk
        chunk = self._body[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("feeds.common.fetch")

    allow_all = Rules(disallow=(), allow=(), loaded=True, source="test: allow-all")
    deny_all = Rules()  # unloaded: fails closed

    # ── fails closed: an unloaded ruleset refuses before any opener runs ─────
    calls = []
    def _tripwire(url, *, timeout):
        calls.append(url); raise AssertionError("opener must not be called when robots denies")

    r = fetch("TEST", "https://x.invalid/a", rules=deny_all, opener=_tripwire)
    check(r.source_behaviour == BLOCKED, "a fetch through a blocked robots path fails CLOSED (BLOCKED), not empty-but-ACCESSIBLE")
    check(not r.content and not calls, "...and never even asks the transport for bytes")
    check("not loaded" in r.note, f"...and says why: {r.note}")
    check(r.url == "https://x.invalid/a", "the FetchResult still names the entry url it refused")

    # ── an explicit Disallow behaves the same way, via real robots.parse() ──
    from checker.robots import parse as robots_parse
    disallowing = robots_parse("User-agent: *\nDisallow: /secret/\n")
    r = fetch("TEST", "https://x.invalid/secret/x", rules=disallowing, opener=_tripwire)
    check(r.source_behaviour == BLOCKED, "an explicit robots Disallow also fails closed")

    # ── a plain 200 ───────────────────────────────────────────────────────────
    def opener_200(url, *, timeout):
        return _FakeResponse(200, b"<sdn>hello</sdn>", headers={"Content-Length": "16"})

    r = fetch("SDN_TEST", "https://ofac.example.gov/sdn.xml", rules=allow_all, opener=opener_200)
    check(r.source_behaviour == ACCESSIBLE and r.content == b"<sdn>hello</sdn>",
          "an allowed, answered fetch returns ACCESSIBLE with the real bytes")
    check(r.sha256 == _sha256(b"<sdn>hello</sdn>").hexdigest(), "the hash matches the actual content")
    check(r.resolved_host == "", "no redirect happened, so resolved_host stays empty")

    # ── a 404 is evidence of nothing ─────────────────────────────────────────
    def opener_404(url, *, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    r = fetch("TEST", "https://x.gov/missing", rules=allow_all, opener=opener_404)
    check(r.source_behaviour == NOT_FOUND and not r.content,
          "a 404 comes back as NOT_FOUND with no content -- never as an empty success")

    # ── a network failure ────────────────────────────────────────────────────
    def opener_down(url, *, timeout):
        raise OSError("Connection refused")

    r = fetch("TEST", "https://x.gov/y", rules=allow_all, opener=opener_down)
    check(r.source_behaviour == UNREACHABLE, "a socket failure is UNREACHABLE, distinct from NOT_FOUND")

    # ── a 403 (WAF) is BLOCKED, not UNREACHABLE ──────────────────────────────
    def opener_403(url, *, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    r = fetch("TEST", "https://x.gov/z", rules=allow_all, opener=opener_403)
    check(r.source_behaviour == BLOCKED and r.http_status == 403,
          "a 403 is BLOCKED, distinct from a socket-level UNREACHABLE")

    # ── a 5xx is UNREACHABLE ("no real answer"), not BLOCKED ────────────────
    def opener_503(url, *, timeout):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)

    r = fetch("TEST", "https://x.gov/w", rules=allow_all, opener=opener_503)
    check(r.source_behaviour == UNREACHABLE, "a 5xx is UNREACHABLE, not confused with a WAF block")

    # ── the OFAC-shaped case: cross-host redirect refused by default ────────
    import email.message

    def opener_redirect(url, *, timeout):
        hdrs = email.message.Message()
        hdrs["Location"] = ("https://wc2h-sls-prod-public-published.s3.us-gov-west-1"
                            ".amazonaws.com/sdn.xml?X-Amz-Expires=3600")
        raise urllib.error.HTTPError(url, 302, "Found", hdrs, None)

    r = fetch("OFAC_SDN", "https://www.treasury.gov/ofac/downloads/sdn.xml",
             rules=allow_all, opener=opener_redirect)
    check(r.source_behaviour == BLOCKED,
          "a cross-host redirect is refused by DEFAULT, not silently followed")
    check(r.url == "https://www.treasury.gov/ofac/downloads/sdn.xml",
          "...and the entry url is preserved even though the redirect was refused")
    check("s3.us-gov-west-1" in r.note and "not in allow_redirect_hosts" in r.note,
          f"...and both hosts are named in the record: {r.note}")
    check(not r.content, "a refused redirect carries no bytes")

    # ── the same redirect, explicitly trusted, is followed -- and identity holds ─
    def opener_redirect_then_body(url, *, timeout):
        if "treasury.gov" in url:
            hdrs = email.message.Message()
            hdrs["Location"] = ("https://wc2h-sls-prod-public-published.s3.us-gov-west-1"
                                ".amazonaws.com/sdn.xml?X-Amz-Expires=3600")
            raise urllib.error.HTTPError(url, 302, "Found", hdrs, None)
        return _FakeResponse(200, b"<sdn>the real 29MB-shaped payload</sdn>")

    r = fetch("OFAC_SDN", "https://www.treasury.gov/ofac/downloads/sdn.xml",
             rules=allow_all, opener=opener_redirect_then_body,
             allow_redirect_hosts=("wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",))
    check(r.source_behaviour == ACCESSIBLE, "an explicitly-trusted redirect target is followed")
    check(r.url == "https://www.treasury.gov/ofac/downloads/sdn.xml",
          "...but the FetchResult's identity is STILL the entry url, never the signed S3 link")
    check(r.resolved_host == "wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com",
          "...and the resolved host is recorded separately, as metadata about the transaction")
    check(b"29MB-shaped payload" in r.content, "the actual bytes come from the followed redirect")

    # ── size cap: declared Content-Length over the cap refuses before reading ─
    def opener_huge_declared(url, *, timeout):
        return _FakeResponse(200, b"x" * 10, headers={"Content-Length": "999999999"})

    r = fetch("TEST", "https://x.gov/huge", rules=allow_all, opener=opener_huge_declared, max_bytes=1024)
    check(r.source_behaviour == BLOCKED and "exceeds" in r.note,
          f"a declared Content-Length over max_bytes refuses without reading the body: {r.note}")

    # ── size cap: an undeclared body that actually exceeds the cap is caught too ─
    def opener_huge_actual(url, *, timeout):
        return _FakeResponse(200, b"y" * 5000)  # no Content-Length header at all

    r = fetch("TEST", "https://x.gov/huge2", rules=allow_all, opener=opener_huge_actual, max_bytes=1024)
    check(r.source_behaviour == BLOCKED and not r.content,
          "an oversized body with no declared length is still caught mid-read, never buffered whole")

    # ── size cap: a body just under the cap is fine ──────────────────────────
    def opener_ok_size(url, *, timeout):
        return _FakeResponse(200, b"z" * 1000)

    r = fetch("TEST", "https://x.gov/ok", rules=allow_all, opener=opener_ok_size, max_bytes=1024)
    check(r.source_behaviour == ACCESSIBLE and len(r.content) == 1000,
          "a body under the cap is returned whole")

    # ── DEFAULT_MAX_BYTES actually reflects the measured OFAC payload ───────
    check(DEFAULT_MAX_BYTES > 29_076_910,
          f"the default cap ({DEFAULT_MAX_BYTES}) clears the measured SDN payload size (29,076,910)")

    # ---- RT-04: a body shorter than its declared Content-Length ----------------
    short = _FakeResponse(200, b"half a document", headers={"Content-Length": "999999"})
    r = fetch("t", "https://example.gov/x", rules=allow_all,
              opener=lambda url, *, timeout: short)
    check(r.source_behaviour == UNREACHABLE and r.content == b"",
          "a truncated transfer is refused, carrying no bytes")
    check("truncated" in r.note,
          "...and says so, rather than presenting a partial document as complete")
    exact = _FakeResponse(200, b"whole", headers={"Content-Length": "5"})
    r2 = fetch("t", "https://example.gov/x", rules=allow_all,
               opener=lambda url, *, timeout: exact)
    check(r2.source_behaviour == ACCESSIBLE and r2.content == b"whole",
          "a body that matches its declared length still succeeds")
    nolen = _FakeResponse(200, b"no header here")
    r3 = fetch("t", "https://example.gov/x", rules=allow_all,
               opener=lambda url, *, timeout: nolen)
    check(r3.source_behaviour == ACCESSIBLE,
          "no Content-Length at all is not treated as truncation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
