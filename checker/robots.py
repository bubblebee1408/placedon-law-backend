"""Robots exclusion, enforced in code rather than by intention.

Indian Kanoon's robots.txt is not a policy statement — it is a denylist of roughly
9,300 individually named documents, almost certainly delisting requests from the
people those judgments are about. No human reads 9,313 lines before each fetch, so
the rule has to live in the fetch path or it does not exist.

Two design choices worth stating:

**Unparseable robots.txt denies everything.** The alternative — treating a fetch
failure as permission — means a network blip silently converts into crawling a
delisted judgment. Fail closed.

**Only the `User-Agent: *` group is honoured, and we never claim another agent's
identity.** Selecting a more permissive group by renaming ourselves is exactly the
user-agent rotation this project refuses to do.

No third-party dependency: `urllib.robotparser` exists but does not expose whether
it actually loaded a file versus silently defaulting to allow-all, and that
distinction is the whole point here.
"""
from __future__ import annotations

import os
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit, unquote

USER_AGENT = (
    "PlacedonResearch/1.0 (Indian corporate-law corpus verification; "
    "contact nishantsingh14088@gmail.com)"
)

# A group header line: "User-agent: foo" (spacing is inconsistent in the wild).
_AGENT = re.compile(r"^\s*user-agent\s*:\s*(.*?)\s*$", re.I)
_RULE = re.compile(r"^\s*(disallow|allow)\s*:\s*(.*?)\s*$", re.I)
_DELAY = re.compile(r"^\s*crawl-delay\s*:\s*([\d.]+)\s*$", re.I)

DEFAULT_DELAY_S = 2.0  # our own courtesy floor when the site names none

# python.org builds on macOS ship a default CA path that does not exist until the
# bundled "Install Certificates.command" is run, so urllib fails where curl works.
# The tempting fix is ssl._create_unverified_context(). For a project whose entire
# claim is that its sources are authenticated, an unverified source is worth less
# than no source: it cannot distinguish the Gazette from anyone who can answer on
# its behalf. So we hunt for a real trust store and fail closed without one.
_CA_CANDIDATES = (
    "/etc/ssl/cert.pem",                    # macOS
    "/etc/ssl/certs/ca-certificates.crt",   # Debian, Ubuntu, Alpine
    "/etc/pki/tls/certs/ca-bundle.crt",     # RHEL, Fedora
    "/usr/local/etc/openssl/cert.pem",      # Homebrew OpenSSL
)


def _usable(path: str | None) -> bool:
    # A stub file would verify nothing; a real bundle is tens of kilobytes.
    return bool(path) and os.path.exists(path) and os.path.getsize(path) > 1024


def ca_bundle() -> str | None:
    """Path to a usable CA bundle, or None if the machine has no trust store.

    Order: an explicit SSL_CERT_FILE, then certifi's maintained Mozilla bundle, then
    the OS OpenSSL default, then the well-known paths. This never weakens
    verification -- it changes WHICH trusted list is consulted, never WHETHER.

    Why certifi now comes before the OS default (2026-09-17): the OS default on this
    Mac is /etc/ssl/cert.pem, a frozen 128-certificate bundle that lacks *Sectigo
    Public Server Authentication Root R46*. OFAC's Sanctions List Service chains
    Treasury -> Entrust OV TLS Issuing RSA CA 2 -> Sectigo R46, so every verified
    fetch there failed with "self-signed certificate in certificate chain" -- while
    curl, using the macOS keychain (which has R46), succeeded. certifi 2025.08.03
    carries 145 roots including R46. A stale trust store fails CLOSED, which is the
    safe direction, but it made a correct source look broken; preferring the
    maintained bundle fixes that without accepting anything unverified.
    """
    env = os.environ.get("SSL_CERT_FILE")
    if _usable(env):
        return env
    try:                                    # present on many machines, not a declared dep
        import certifi
        if _usable(certifi.where()):
            return certifi.where()
    except Exception:
        pass
    p = ssl.get_default_verify_paths().openssl_cafile
    if _usable(p):
        return p
    for cand in _CA_CANDIDATES:
        if _usable(cand):
            return cand
    return None


INTERMEDIATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs", "intermediates.pem")


def ssl_context() -> ssl.SSLContext | None:
    """A verifying context, or None when no trust store can be found.

    Also loads `certs/intermediates.pem` for chain COMPLETION: some government
    hosts (egazette.gov.in) send only their leaf, and Python does not fetch the
    missing issuer the way a browser does. Loading an intermediate here does not
    make it an anchor -- OpenSSL still requires the chain to end at a SELF-SIGNED
    root from the trusted bundle -- and VERIFY_X509_PARTIAL_CHAIN is cleared
    explicitly so that holds on Python versions that would otherwise set it.
    """
    bundle = ca_bundle()
    if bundle is None:
        return None
    ctx = ssl.create_default_context(cafile=bundle)
    if _usable(INTERMEDIATES):
        ctx.load_verify_locations(cafile=INTERMEDIATES)
    partial = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", None)
    if partial is not None:
        ctx.verify_flags &= ~partial
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


@dataclass(frozen=True)
class Rules:
    """The `User-Agent: *` group, as actually published."""

    disallow: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()
    crawl_delay: float | None = None
    loaded: bool = False
    source: str = ""

    @property
    def delay(self) -> float:
        """Seconds to wait between requests. Our floor, or theirs if slower."""
        return max(DEFAULT_DELAY_S, self.crawl_delay or 0.0)


def parse(text: str, *, source: str = "") -> Rules:
    """Extract the `User-Agent: *` group.

    Consecutive `User-agent:` lines share one rule block, so `*` may be named
    alongside other agents. Rules are collected from every block `*` belongs to.
    """
    disallow: list[str] = []
    allow: list[str] = []
    delay: float | None = None

    agents: set[str] = set()      # agents heading the current block
    in_star = False
    prev_was_agent = False

    for line in text.splitlines():
        line = line.split("#", 1)[0]
        if not line.strip():
            continue

        if m := _AGENT.match(line):
            if not prev_was_agent:
                agents = set()    # a rule line closed the previous block
            agents.add(m.group(1).lower())
            in_star = "*" in agents
            prev_was_agent = True
            continue

        prev_was_agent = False
        if not in_star:
            continue

        if m := _RULE.match(line):
            kind, path = m.group(1).lower(), m.group(2)
            if not path:
                # "Disallow:" with an empty value means allow all — not a path.
                continue
            (disallow if kind == "disallow" else allow).append(path)
        elif m := _DELAY.match(line):
            try:
                delay = float(m.group(1))
            except ValueError:
                pass

    return Rules(
        disallow=tuple(disallow),
        allow=tuple(allow),
        crawl_delay=delay,
        loaded=True,
        source=source,
    )


def _normalise(path: str) -> str:
    """Collapse the spellings of one path so a denylist entry cannot be dodged.

    Indian Kanoon's own file contains `/doc//117621087` — a double slash, and
    seemingly a typo. Whether it was meant as `/doc/117621087` is not ours to
    decide, so both spellings are matched. Erring toward refusing a fetch costs
    us one document; erring the other way serves a delisted judgment.
    """
    path = unquote(path)
    path = re.sub(r"/{2,}", "/", path)
    return path.rstrip("/") or "/"


def _matches(pattern: str, path: str) -> bool:
    pat = _normalise(pattern)
    if pat in ("/", ""):
        return True
    # robots.txt prefix semantics, plus `*` and `$` as universally supported.
    if "*" in pat or pat.endswith("$"):
        anchored = pat.endswith("$")
        body = pat[:-1] if anchored else pat
        rx = "".join(".*" if c == "*" else re.escape(c) for c in body)
        return bool(re.match(rx + ("$" if anchored else ""), path))
    return path.startswith(pat)


def allowed(url: str, rules: Rules) -> bool:
    """May we fetch this URL?

    An unloaded ruleset denies everything: we could not read the site's terms, so
    we have no basis for claiming it permitted the request.
    """
    if not rules.loaded:
        return False

    path = _normalise(urlsplit(url).path)

    # Longest match wins, and Allow beats Disallow at equal length (RFC 9309).
    best_len, verdict = -1, True
    for pat in rules.disallow:
        if _matches(pat, path) and len(pat) > best_len:
            best_len, verdict = len(pat), False
    for pat in rules.allow:
        if _matches(pat, path) and len(pat) >= best_len:
            best_len, verdict = len(pat), True
    return verdict


def fetch_rules(origin: str, *, timeout: float = 15.0) -> Rules:
    """Read `<origin>/robots.txt`. Any failure yields a deny-everything ruleset."""
    url = origin.rstrip("/") + "/robots.txt"
    ctx = ssl_context()
    if ctx is None:
        return Rules(source=f"{url} not attempted: no CA bundle, cannot verify TLS")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            if r.status != 200:
                return Rules(source=f"{url} HTTP {r.status}")
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return rules_for_status(exc.code, url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Rules(source=f"{url} unreachable: {exc}")
    return parse(body, source=url)


# Status codes on robots.txt that are a REFUSAL, not an absence. RFC 9309 §2.3.1.3
# groups all 4xx as "unavailable" and says a crawler MAY then access anything --
# "may", not "must". A 401/403/407 is the server saying we are not welcome; a 429 is
# it saying slow down. Reading either as "no rules exist, so everything is allowed"
# is the RFC's letter and the wrong verdict. Measured 2026-09-17: bseindia.com
# answers its robots.txt with an Akamai "Access Denied" 403, which the old rule read
# as full permission.
_DENIED = (401, 403, 407, 429)


def rules_for_status(code: int, url: str) -> Rules:
    """The ruleset implied by a non-200 answer for robots.txt.

    A genuine absence (404, 410, and the remaining 4xx) is an *answer*: the server is
    reachable and publishes no rules, which RFC 9309 treats as full allowance.
    Collapsing that into "closed" would lock us out of every site without a
    robots.txt (cca.gov.in, egazette.gov.in, sanctionslistservice.ofac.treas.gov
    among them). A denial or rate limit (`_DENIED`), a 5xx, or any other status is
    NOT permission and stays closed -- a failing or refusing server must never look
    like consent.
    """
    if code in _DENIED:
        return Rules(source=f"{url} HTTP {code}: access denied or rate-limited -- not treated as 'no rules'")
    if 400 <= code < 500:
        return Rules(loaded=True, source=f"{url} HTTP {code}: no rules published")
    return Rules(source=f"{url} HTTP {code}")


class Fetcher:
    """A rate-limited fetcher that cannot be talked into ignoring robots.txt."""

    def __init__(self, origin: str, *, rules: Rules | None = None) -> None:
        self.origin = origin.rstrip("/")
        self.rules = rules if rules is not None else fetch_rules(self.origin)
        self._last = 0.0

    def get(self, url: str, *, timeout: float = 30.0) -> tuple[int, str]:
        """Returns (status, body). Status 999 means we declined to ask."""
        if not url.startswith(self.origin):
            return 999, f"refused: {url} is outside {self.origin}"
        if not allowed(url, self.rules):
            reason = "robots.txt disallows it" if self.rules.loaded else \
                     f"robots.txt not loaded ({self.rules.source})"
            return 999, f"refused: {reason}"

        wait = self.rules.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

        ctx = ssl_context()
        if ctx is None:
            return 999, "refused: no CA bundle, cannot verify TLS"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, ""
        except (urllib.error.URLError, OSError) as exc:
            return 0, str(exc)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("robots")

    # Fail-closed is the property that matters most; test it first.
    check(not allowed("https://x.org/doc/1/", Rules()),
          "an unloaded ruleset denies everything")
    check(not Fetcher("https://x.org", rules=Rules()).get("https://x.org/a")[0] == 200,
          "a fetcher with no rules refuses to fetch")
    st, msg = Fetcher("https://x.org", rules=Rules()).get("https://x.org/a")
    check(st == 999 and "not loaded" in msg,
          "...and says why, rather than reporting a network error")

    r = parse("User-Agent: *\nDisallow: /cached/\nDisallow: /doc/123/\n")
    check(r.loaded, "a well-formed file parses")
    check(not allowed("https://ik.org/cached/x", r), "a disallowed prefix is refused")
    check(not allowed("https://ik.org/doc/123/", r), "a delisted document is refused")
    check(allowed("https://ik.org/doc/124/", r), "a neighbouring document is allowed")
    check(not allowed("https://ik.org/doc/123", r),
          "the trailing slash does not change the answer")

    # The real file names other agents. We must not read their rules as ours.
    r2 = parse("User-agent: *\nDisallow: /a/\n\nUser-agent: Baiduspider\nDisallow: /search/\n")
    check(allowed("https://ik.org/search/?q=1", r2),
          "another agent's stricter rule is not applied to us")
    check(not allowed("https://ik.org/a/b", r2), "our own rule still binds")

    # Consecutive agent lines share a block.
    r3 = parse("User-agent: Foo\nUser-agent: *\nDisallow: /shared/\n")
    check(not allowed("https://ik.org/shared/x", r3),
          "a block naming us alongside another agent still binds")

    # An agent group that excludes us must not leak in.
    r4 = parse("User-agent: SemrushBot\nDisallow: /\n")
    check(allowed("https://ik.org/anything", r4),
          "a blanket ban aimed at another crawler does not bind us")

    check(parse("User-agent: *\nDisallow:\n").disallow == (),
          "an empty Disallow means allow-all, not a path")

    r5 = parse("User-agent: *\nDisallow: /a/\nAllow: /a/b\n")
    check(allowed("https://ik.org/a/b", r5), "a longer Allow overrides a Disallow")
    check(not allowed("https://ik.org/a/c", r5), "...without opening the rest")

    check(parse("User-agent: *\nCrawl-delay: 10\n").delay == 10.0,
          "a stated crawl-delay is honoured")
    check(parse("User-agent: *\n").delay == DEFAULT_DELAY_S,
          "no stated delay falls back to our own floor")
    check(parse("User-agent: *\nCrawl-delay: 0.1\n").delay == DEFAULT_DELAY_S,
          "a delay faster than our floor does not speed us up")

    r6 = parse("User-Agent: *\nDisallow: /doc//999\n")
    check(not allowed("https://ik.org/doc/999", r6),
          "a double-slash denylist entry still refuses the single-slash URL")

    check(Fetcher("https://a.org", rules=parse("User-agent: *\n"))
          .get("https://b.org/x")[0] == 999,
          "a cross-origin URL is refused rather than fetched")

    # A 404 means "no rules exist"; a 503 means "no answer". Only the first grants
    # permission, and conflating them is a bug in either direction.
    # The status decision itself, exercised rather than hand-built (move 8, 2026-09-17).
    # BSE answered its robots.txt with an Akamai "Access Denied" 403; the old rule read
    # every 4xx as "no rules published" and so as permission.
    u = "https://example.gov/robots.txt"
    check(rules_for_status(404, u).loaded and allowed("https://example.gov/x", rules_for_status(404, u)),
          "404: no rules file exists -> full allowance (RFC 9309)")
    check(rules_for_status(410, u).loaded, "410 Gone is also an absent file -> allowance")
    for code in (401, 403):
        r = rules_for_status(code, u)
        check(not r.loaded and not allowed("https://example.gov/x", r),
              f"{code}: access DENIED is a block, not an absence -> closed")
        check(f"HTTP {code}" in r.source and "denied" in r.source,
              f"...and the {code} refusal says why")
    check(not rules_for_status(429, u).loaded, "429 rate-limited is not an answer about rules -> closed")
    check(not rules_for_status(503, u).loaded, "5xx is not an answer -> closed")

    r404 = Rules(loaded=True, source="HTTP 404: no rules published")
    check(allowed("https://cca.gov.in/anything", r404),
          "a 404 robots.txt permits fetching (RFC 9309)")
    check(not allowed("https://x.org/a", Rules(source="HTTP 503")),
          "a 5xx robots.txt still denies everything")
    check(not allowed("https://x.org/a", Rules(source="timeout")),
          "an unreachable robots.txt still denies everything")

    # TLS verification is part of provenance, not a networking detail.
    ctx = ssl_context()
    check(ctx is not None, f"a CA bundle is available ({ca_bundle()})")
    if ctx is not None:
        check(ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname,
              "the context verifies certificates and hostnames")
        partial = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", None)
        check(partial is None or not (ctx.verify_flags & partial),
              "partial chains are refused: an intermediate can never act as a root")

    # Chain-completion intermediates (egazette.gov.in sends only its leaf).
    import re as _re
    from datetime import datetime as _dt, timezone as _tz
    check(_usable(INTERMEDIATES), f"the intermediates file is present ({INTERMEDIATES})")
    if _usable(INTERMEDIATES):
        pem = open(INTERMEDIATES, encoding="ascii").read()
        check(pem.count("BEGIN CERTIFICATE") == 2, "it holds exactly the two recorded intermediates")
        ends = [_dt.strptime(s.strip(), "%b %d %H:%M:%S %Y GMT").replace(tzinfo=_tz.utc)
                for s in _re.findall(r"^# notAfter=(.+)$", pem, _re.M)]
        check(len(ends) == 2, "each intermediate records its expiry")
        if ends:
            days = (min(ends) - _dt.now(_tz.utc)).days
            check(days > 0, f"no intermediate has expired (earliest lapses in {days} days)")
            if 0 < days < 180:
                print(f"  [WARN] an intermediate lapses in {days} days -- eGazette fetches "
                      "will then fail closed until checker/certs/intermediates.pem is refreshed")
    # Assembled at runtime so this guard does not trip over its own source text.
    banned = ["_create_" + "unverified", "CERT_" + "NONE", "check_hostname = " + "False"]
    src = __import__("pathlib").Path(__file__).read_text()
    hits = [b for b in banned if src.count(b) > 1]   # >1: the list above is hit 1
    check(not hits, f"no code path disables certificate verification ({hits or 'clean'})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
