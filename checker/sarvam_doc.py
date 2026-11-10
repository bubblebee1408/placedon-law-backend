"""Sarvam Document AI Parse: a PDF in, stitched Markdown out. OFF by default, public documents only.

Not wired into any ingest path. The client upload path (`gateway/verbs/documents.py`,
`agents/vault_ingest.py`) neither imports this module nor reads its switch; the self-test
asserts that. The only entry point is the CLI, for trying the reader on PUBLIC documents:

    PLACEDON_DOC_READER=sarvam PLACEDON_SARVAM_PUBLIC_ONLY_ACK=1 SARVAM_API_KEY=... \\
        python3 -m checker.sarvam_doc corpus/sources/gsr880e_2025.pdf > out.md
    python3 checker/sarvam_doc.py --test          # the keyless, offline self-test

## Why a second Sarvam module

`checker/sarvam_model.py` is the Digitise adapter (the OCR bake-off candidate). Sarvam's
own docs now say "Document AI supersedes the earlier Document Digitization API" (D1) and
that Parse is the operation for "the whole page as text ... Output: HTML, Markdown, or
JSON". Parse returns its output differently -- a ZIP behind a presigned download URL, not
a JSON results body -- so it is a different wire, and this module adds only that wire. The
splitter, multipart builder, pacer, job/status parsers, key handling, error classes and the
privacy guard are REUSED from sarvam_model, not re-implemented.

## What was pinned, from which page (fetched 2026-11-10 as raw `.md`)

    D1  https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview
    D2  https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/how-to/parse.md
    D3  https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md
    D4  https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/job-lifecycle.md
    D5  https://docs.sarvam.ai/api-reference/doc-ai/job/parse.md
    D6  https://docs.sarvam.ai/api-reference/doc-ai/job/download-url.md

- Submit: `POST https://api.sarvam.ai/doc-ai/v1/job/parse`, multipart/form-data, `file`,
  `language` (BCP-47), `output_format` (`md`; `"markdown"` is a 400). Header
  `api-subscription-key`. 201 -> `{job_id, status, run_id}`. ONE call creates AND starts
  the job (D1, D2, D5) -- the create -> upload -> start flow is the LEGACY Document
  Digitization API (D3, "Legacy" section), which new integrations are told not to use.
- Poll: `GET /doc-ai/v1/job/{job_id}/status`; terminal = completed, partially_completed,
  failed, rejected; non-terminal = pending, running (D4).
- Fetch: `GET /doc-ai/v1/job/{job_id}/download-url` -> `{method, url, expires_at,
  headers?}` (D6); 409 before terminal (D4, D6). The link "is a plain GET and needs no API
  key header" (D2) -- so the key is NEVER sent to it. The ZIP holds `manifest.json`,
  `<file>/<file>.md` and `<file>/metadata/page_NNN.json` (D2).
- Limits: 10 pages per PDF, 10 requests/minute on all plans (D3). See AMBIGUOUS.
- Errors: 400, 402/403 billing, 404, 409, 413, 422, 429 "rate or admission limit",
  503 "billing unavailable" (D4).

## AMBIGUOUS in the docs -- the conservative reading is used, never a guess

- Page cap: D2 says Parse takes "30 pages per PDF or ZIP"; D3 says "10 pages per PDF ...
  10-page cap per job". 10 is used: a 10-page part is valid under both.
- Rate limit: D3 says "10 requests/minute (all plans)"; the limits page says "Requests per
  minute vary by plan and operation". Every request -- submit, poll, download-url, and the
  presigned download itself -- is paced as if 10/min binds.
- `output_format` is in D2's parameter table but absent from D5's body schema. Sent as
  `md`, per D2's examples.
- Page boundaries INSIDE the Markdown file are not documented, and neither is the shape of
  `metadata/page_NNN.json`. So page markers are emitted per PART (pages a-b), which is the
  finest boundary we actually know. Not per page.
- `partially_completed`: D4 says fetch the output, then check `usage.pages_failed`. Which
  pages failed is not said. The part is kept, its marker says PARTIAL with the count, and
  `ParseResult.complete` is False. Nothing is presented as whole that is not.
- Whether the presigned download host is fixed is not documented, so only https is
  required of it, and it never receives the key.

## Guards (all before a byte is read for upload)

1. `PLACEDON_SARVAM_PUBLIC_ONLY_ACK=1` must be set, or `SarvamNotAcknowledged`: client
   documents need Sarvam's WRITTEN data terms first (their privacy policy defaults to
   training on uploads -- see sarvam_model's S8 note).
2. `PLACEDON_DOC_READER=sarvam` must be set, or `ReaderDisabled`. Unset is the default,
   and unset changes nothing anywhere.
3. `sarvam_model.privacy_check`: a public file this repo holds at HEAD (corpus/sources/,
   corpus/testdocs/), or the founder's `.env` training opt-out line.

## Errors

429 and 5xx are retried ONCE (after RETRY_WAIT_S); then `SarvamRateLimited` /
`SarvamHTTPError`. Any other HTTP status is a `SarvamHTTPError` at once, with `.status`.
Every message is redacted of the key and carries no document content.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from checker import sarvam_model as sm

API = "https://api.sarvam.ai/doc-ai/v1"
READER_ENV = "PLACEDON_DOC_READER"
READER_VALUE = "sarvam"
ACK_ENV = "PLACEDON_SARVAM_PUBLIC_ONLY_ACK"
OUTPUT_FORMAT = "md"
RETRY_WAIT_S = 10.0
MAX_WAIT_S = sm.MAX_WAIT_S       # per job, bounded: polls past this raise, never hang
TIMEOUT_S = sm.TIMEOUT_S         # every socket call is timed
MAX_MD_BYTES = 50 * 1024 * 1024  # declared size of the .md member, checked before reading


class ReaderDisabled(sm.SarvamError):
    """PLACEDON_DOC_READER is not `sarvam`. The default; nothing is sent."""


class SarvamNotAcknowledged(sm.SarvamPrivacyRefused):
    """PLACEDON_SARVAM_PUBLIC_ONLY_ACK=1 is not set."""


class SarvamHTTPError(sm.SarvamServiceError):
    def __init__(self, msg: str, status: int):
        super().__init__(msg)
        self.status = status


class SarvamRateLimited(SarvamHTTPError):
    """429 twice in a row: wait a minute, do not hammer."""


@dataclass(frozen=True)
class PartResult:
    first_page: int
    last_page: int
    job_id: str
    status: str                  # completed | partially_completed
    pages_failed: int | None
    markdown: str


@dataclass(frozen=True)
class ParseResult:
    source: str
    n_pages: int
    parts: tuple[PartResult, ...]

    @property
    def complete(self) -> bool:
        return all(p.status == "completed" for p in self.parts)

    def markdown(self) -> str:
        """The parts in page order, each under a marker naming its pages and job."""
        out = []
        for p in self.parts:
            flag = "" if p.status == "completed" else f" PARTIAL pages_failed={p.pages_failed}"
            out.append(f"<!-- sarvam-doc: pages {p.first_page}-{p.last_page} of {self.n_pages}"
                       f" job={p.job_id}{flag} -->\n\n{p.markdown.strip()}\n")
        return "\n".join(out)


def enabled() -> bool:
    return (os.getenv(READER_ENV) or "").strip().lower() == READER_VALUE


def guard() -> None:
    """Refuse unless both the public-only acknowledgement and the switch are set."""
    if (os.getenv(ACK_ENV) or "").strip() != "1":
        raise SarvamNotAcknowledged(
            f"REFUSED: set {ACK_ENV}=1 to confirm this is a PUBLIC document. Client "
            f"documents must not be sent to Sarvam until Sarvam's WRITTEN data terms "
            f"(retention, no training on uploads) are in hand -- its privacy policy trains "
            f"on uploads by default. Nothing was sent.")
    if not enabled():
        raise ReaderDisabled(f"{READER_ENV} is not '{READER_VALUE}' (default: unset). "
                             f"The Sarvam reader is off; nothing was sent.")


# ── the wire ──────────────────────────────────────────────────────────────────
def _urlopen(method: str, url: str, body: bytes | None, headers: dict) -> tuple[int, bytes]:
    """The real transport: (status, body). An HTTP error status is RETURNED, not raised,
    so retry/typing lives in one place (`_request`) the fake transport also exercises."""
    from checker.robots import ssl_context
    ctx = ssl_context()
    if ctx is None:
        raise sm.SarvamUnavailable("no CA trust store; refusing to call Sarvam unverified")
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _request(call, sleep, method: str, url: str, body: bytes | None = None,
             headers: dict | None = None, key: str | None = None) -> bytes:
    where = f"{method} {urlparse(url).path}"          # never the query: presigned tokens
    for attempt in (1, 2):
        try:
            code, raw = call(method, url, body, dict(headers or {}))
        except sm.SarvamError:
            raise
        except OSError as e:     # URLError, timeout, reset
            raise sm.SarvamServiceError(
                f"Sarvam unreachable on {where} ({type(e).__name__}: "
                f"{sm._redact(str(e), key)[:120]})") from None
        if 200 <= code < 300:
            return raw
        retryable = code == 429 or code >= 500
        if retryable and attempt == 1:
            sleep(RETRY_WAIT_S)
            continue
        detail = sm._redact(sm._problem(raw[:600].decode("utf-8", "replace")), key)[:300]
        cls = SarvamRateLimited if code == 429 else SarvamHTTPError
        tried = " (after one retry)" if retryable else ""
        raise cls(f"Sarvam HTTP {code} on {where}{tried}: {detail}", code)
    raise AssertionError("unreachable")                                 # pragma: no cover


def _json(raw: bytes, where: str) -> dict:
    try:
        d = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise sm.SarvamBadResponse(f"{where}: not a JSON body") from None
    if not isinstance(d, dict):
        raise sm.SarvamBadResponse(f"{where}: not a JSON object")
    return d


def _markdown_from_zip(raw: bytes, job_id: str) -> str:
    """The one primary .md in the output ZIP (D2). Metadata JSON is not read: its shape is
    undocumented. Zero or several .md files is refused rather than chosen between."""
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise sm.SarvamBadResponse(f"job {job_id}: download is not a ZIP") from None
    with z:
        mds = [i for i in z.infolist() if i.filename.endswith(".md")
               and "/metadata/" not in f"/{i.filename}"]
        if len(mds) != 1:
            raise sm.SarvamBadResponse(
                f"job {job_id}: expected exactly one .md in the output ZIP, found {len(mds)}")
        if mds[0].file_size > MAX_MD_BYTES:
            raise sm.SarvamBadResponse(f"job {job_id}: .md declares {mds[0].file_size} bytes")
        try:
            return z.read(mds[0]).decode("utf-8")
        except (UnicodeDecodeError, zipfile.BadZipFile, OSError) as e:
            raise sm.SarvamBadResponse(f"job {job_id}: .md unreadable ({type(e).__name__})") from None


def _run_part(part: sm.Part, *, language: str, req, clock, key: str,
              max_wait: float) -> PartResult:
    auth = {"api-subscription-key": key}
    body, ctype = sm.build_multipart(
        [("language", language), ("output_format", OUTPUT_FORMAT)],
        [("file", part.filename, part.content_type, part.data)], uuid.uuid4().hex)
    job_id, _, _ = sm.parse_created(_json(
        req("POST", f"{API}/job/parse", body, auth | {"Content-Type": ctype}), "submit"))
    start = clock()
    while True:
        st = sm.parse_status(_json(req("GET", f"{API}/job/{job_id}/status", None, auth),
                                   "status"))
        if st.status in sm.TERMINAL:
            break
        if st.status not in sm.NON_TERMINAL:
            raise sm.SarvamBadResponse(f"job {job_id}: undocumented status {st.status!r}")
        if clock() - start > max_wait:
            raise sm.SarvamServiceError(
                f"job {job_id} not terminal within {max_wait}s (last: {st.status}). "
                f"Not an empty document; re-poll the job id later.")
    last = part.first_page + part.n_pages - 1
    if st.status in ("failed", "rejected"):
        raise sm.SarvamServiceError(
            f"job {job_id} {st.status} (pages {part.first_page}-{last}). "
            f"A failed job is not an empty document.")
    dl = _json(req("GET", f"{API}/job/{job_id}/download-url", None, auth), "download-url")
    url, method = dl.get("url"), dl.get("method", "GET")
    extra = dl.get("headers") or {}
    if (not isinstance(url, str) or urlparse(url).scheme != "https"
            or str(method).upper() != "GET" or not isinstance(extra, dict)):
        raise sm.SarvamBadResponse(f"job {job_id}: download-url is not an https GET")
    # The key is deliberately absent: D2 says the link needs none, and a presigned URL's
    # host is storage we do not control.
    hdrs = {str(k): str(v) for k, v in extra.items()
            if str(k).lower() != "api-subscription-key"}
    md = _markdown_from_zip(req("GET", url, None, hdrs), job_id)
    return PartResult(part.first_page, last, job_id, st.status, st.pages_failed, md)


def read_markdown(path, *, language: str = "en-IN", env_path: Path | None = None,
                  _transport=None, _sleep=None, _clock=None, _log=None,
                  max_wait: float = MAX_WAIT_S) -> ParseResult:
    """Parse one PDF into Markdown, <= 10-page parts in sequence, paced to 10 req/min."""
    guard()
    clearance = sm.privacy_check(path, env_path=env_path)
    if language not in sm.LANGUAGES:
        raise ValueError(f"language {language!r} is not one of the 23 documented codes")
    if Path(path).suffix.lower() != ".pdf":
        raise ValueError("this reader takes a PDF")
    key = sm._key()
    parts = sm.prepare_parts(path)
    sleep, clock = _sleep or time.sleep, _clock or time.monotonic
    paced = sm._Pacer(_transport or _urlopen, sleep, clock)

    def req(method, url, body=None, headers=None):
        return _request(paced, sleep, method, url, body, headers, key)

    log = _log or (lambda msg: None)
    done = []
    for i, part in enumerate(parts, 1):
        log(f"part {i}/{len(parts)}: pages {part.first_page}-"
            f"{part.first_page + part.n_pages - 1}")
        done.append(_run_part(part, language=language, req=req, clock=clock, key=key,
                              max_wait=max_wait))
    n = done[-1].last_page
    if [p.first_page for p in done] != list(range(1, n + 1, sm.MAX_PAGES_PER_JOB)):
        raise sm.SarvamBadResponse("assembled parts are not in page order")
    return ParseResult(clearance.path, n, tuple(done))


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m checker.sarvam_doc",
                                 description="Sarvam Parse a PUBLIC PDF to Markdown.")
    ap.add_argument("pdf")
    ap.add_argument("--language", default="en-IN")
    ap.add_argument("-o", "--out", help="write Markdown here (default: stdout)")
    a = ap.parse_args(argv)
    say = lambda msg: print(f"sarvam_doc: {msg}", file=sys.stderr)  # noqa: E731
    try:
        res = read_markdown(a.pdf, language=a.language, _log=say)
    except (sm.SarvamError, sm.SarvamBadResponse, ValueError) as e:
        say(f"{type(e).__name__}: {e}")
        return 2
    md = res.markdown()
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    say(f"{res.n_pages} pages in {len(res.parts)} part(s); complete={res.complete}")
    return 0 if res.complete else 3


# ── self-test: no network, no real key, no real document ────────────────────
def _test() -> None:
    import re
    import subprocess
    import tempfile
    from unittest import mock

    import pypdf

    from checker.sarvam_selftest import _multipart_file

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = ok + bool(cond), fail + (not cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    def attempt(fn):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            return e
        return None

    KEY = "sk-FAKE-never-real"
    tmp = Path(tempfile.mkdtemp())
    env_file = tmp / ".env"                 # privacy_check's opt-out line, for a temp PDF
    env_file.write_text(f"{sm.OPT_OUT_NAME}={sm.OPT_OUT_VALUE}\n", encoding="utf-8")
    pdf = tmp / "public-25.pdf"
    w = pypdf.PdfWriter()
    for i in range(25):                     # page i+1 is 200+i wide, so order is checkable
        w.add_blank_page(width=200 + i, height=300)
    with pdf.open("wb") as f:
        w.write(f)

    class Fake:
        """Follows the D2/D4/D6 shapes. `script` overrides a response by call index."""
        def __init__(self, polls=1, final="completed", script=None, zip_mds=1):
            self.t, self.calls, self.parts, self.seen = 0.0, [], [], {}
            self.polls, self.final, self.script, self.zip_mds = polls, final, script or {}, zip_mds

        def clock(self):
            return self.t

        def sleep(self, s):
            self.t += s

        def __call__(self, method, url, body, headers):
            self.calls.append((self.t, method, url, dict(headers)))
            self.t += 0.2
            if len(self.calls) - 1 in self.script:
                return self.script[len(self.calls) - 1]
            u = urlparse(url)
            if u.hostname == "storage.example":
                return 200, self._zip(int(u.path.rsplit("-", 1)[1][:-4]))
            if method == "POST" and u.path == "/doc-ai/v1/job/parse":
                _, data = _multipart_file(body)
                r = pypdf.PdfReader(io.BytesIO(data))
                self.parts.append([int(pg.mediabox.width) - 199 for pg in r.pages])
                jid = f"job-{len(self.parts)}"
                self.seen[jid] = 0
                return 201, json.dumps({"job_id": jid, "status": "pending",
                                        "run_id": "r"}).encode()
            jid = u.path.split("/")[4]
            if u.path.endswith("/status"):
                self.seen[jid] += 1
                st = self.final if self.seen[jid] > self.polls else "running"
                failed = 2 if st == "partially_completed" else 0
                return 200, json.dumps({"job_id": jid, "status": st, "usage": {
                    "pages_total": 10, "pages_failed": failed}}).encode()
            if u.path.endswith("/download-url"):
                return 200, json.dumps({"method": "GET", "expires_at": "x", "url":
                                        f"https://storage.example/o/{jid}.zip?sig=s"}).encode()
            return 404, b"{}"

        def _zip(self, n):
            pages = self.parts[n - 1]
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("manifest.json", "{}")
                for k in range(self.zip_mds):
                    z.writestr(f"p.pdf/p{k}.md", f"# body of pages {pages[0]}-{pages[-1]}\n")
                z.writestr("p.pdf/metadata/page_001.json", "{}")
            return buf.getvalue()

    def run(fake, **kw):
        return read_markdown(pdf, env_path=env_file, _transport=fake, _sleep=fake.sleep,
                             _clock=fake.clock, **kw)

    on = {ACK_ENV: "1", READER_ENV: "sarvam", "SARVAM_API_KEY": KEY}
    print("sarvam_doc")
    net = mock.MagicMock(side_effect=AssertionError("network"))
    with mock.patch.object(urllib.request, "urlopen", net):
        # ── guard and switch ─────────────────────────────────────────────────
        with mock.patch.dict(os.environ, {READER_ENV: "sarvam", "SARVAM_API_KEY": KEY}):
            os.environ.pop(ACK_ENV, None)
            fk = Fake()
            e = attempt(lambda: run(fk))
            check(isinstance(e, SarvamNotAcknowledged) and "WRITTEN data terms" in str(e)
                  and not fk.calls, "no ACK flag: refused, the message names Sarvam's "
                  "written data terms, zero requests")
        with mock.patch.dict(os.environ, {ACK_ENV: "1", "SARVAM_API_KEY": KEY}):
            os.environ.pop(READER_ENV, None)
            fk = Fake()
            e = attempt(lambda: run(fk))
            check(isinstance(e, ReaderDisabled) and not enabled() and not fk.calls,
                  "switch unset (the default): reader off, refused, zero requests")
        files = subprocess.run(["git", "-C", str(sm.ROOT), "ls-files", "*.py"],
                               capture_output=True, text=True).stdout.split()
        hits = [rel for rel in files if rel != "checker/sarvam_doc.py"
                and any(s in (sm.ROOT / rel).read_text(encoding="utf-8", errors="replace")
                        for s in ("sarvam_doc", READER_ENV))]
        ingest = ("gateway/verbs/documents.py", "agents/vault_ingest.py")
        check(len(files) > 100 and not hits and all(f in files for f in ingest),
              f"no other module (incl. the client ingest path {ingest}) imports sarvam_doc "
              f"or reads {READER_ENV}: ingest is untouched ({len(files)} files, hits={hits})")

        with mock.patch.dict(os.environ, on):
            # ── lifecycle, split, order, pacing ──────────────────────────────
            fk = Fake(polls=1)
            res = run(fk)
            check(fk.parts == [list(range(1, 11)), list(range(11, 21)), list(range(21, 26))],
                  "25 pages -> 3 parts of 10/10/5, each holding its own pages in order")
            seq = [(m, urlparse(u).path.rsplit("/", 1)[-1]) for _, m, u, _ in fk.calls]
            one = [("POST", "parse"), ("GET", "status"), ("GET", "status"),
                   ("GET", "download-url"), ("GET", None)]
            check([(m, None if p.endswith(".zip") else p) for m, p in seq] == one * 3,
                  "lifecycle, part by part: submit, poll until terminal, download-url, "
                  "download -- part 2 is submitted only after part 1 is downloaded")
            md = res.markdown()
            marks = re.findall(r"<!-- sarvam-doc: pages (\d+)-(\d+) of 25 job=(\S+) -->", md)
            bodies = [md.index(f"pages {r}\n") for r in ("1-10", "11-20", "21-25")]
            check(marks == [("1", "10", "job-1"), ("11", "20", "job-2"), ("21", "25", "job-3")]
                  and bodies == sorted(bodies), "stitched Markdown: page markers and bodies "
                  "in page order")
            check(res.complete and res.n_pages == 25, "a fully completed run is complete")
            times = [t for t, *_ in fk.calls]
            gaps = [b - a for a, b in zip(times, times[1:])]
            window = max(sum(1 for t in times if s <= t < s + 60) for s in times)
            check(min(gaps) >= 6.0 and window <= 10,
                  f"pacing: every request >= 6 s after the last; max {window} in any 60 s")
            api = [h for _, _, u, h in fk.calls if urlparse(u).hostname == "api.sarvam.ai"]
            store = [h for _, _, u, h in fk.calls if urlparse(u).hostname == "storage.example"]
            check(all(h.get("api-subscription-key") == KEY for h in api) and len(store) == 3
                  and all(KEY not in json.dumps(h) for h in store),
                  "the key goes to api.sarvam.ai only, never to the presigned download")

            # ── retry once on 429/5xx, typed errors otherwise ────────────────
            fk = Fake(script={0: (429, b'{"title":"slow down"}')})
            check(attempt(lambda: run(fk)) is None and fk.calls[1][1] == "POST"
                  and fk.calls[1][0] - fk.calls[0][0] >= RETRY_WAIT_S,
                  "one 429 is retried once, after RETRY_WAIT_S, and the run succeeds")
            body = json.dumps({"title": "busy", "detail": f"key {KEY}"}).encode()
            fk = Fake(script={0: (503, body), 1: (503, body)})
            e = attempt(lambda: run(fk))
            check(isinstance(e, SarvamHTTPError) and e.status == 503 and len(fk.calls) == 2
                  and KEY not in str(e), "5xx twice: SarvamHTTPError(503) after exactly one "
                  "retry, key redacted from the echoed body")
            fk = Fake(script={0: (429, b"{}"), 1: (429, b"{}")})
            e = attempt(lambda: run(fk))
            check(isinstance(e, SarvamRateLimited) and len(fk.calls) == 2,
                  "429 twice: SarvamRateLimited")
            fk = Fake(script={0: (400, b'{"title":"invalid_request_error"}')})
            e = attempt(lambda: run(fk))
            check(isinstance(e, SarvamHTTPError) and e.status == 400 and len(fk.calls) == 1
                  and "invalid_request_error" in str(e), "400: a typed error at once, no retry")

            def down(method, url, body, headers):
                raise urllib.error.URLError(f"down {KEY}")
            fk = Fake()
            e = attempt(lambda: read_markdown(pdf, env_path=env_file, _transport=down,
                                              _sleep=fk.sleep, _clock=fk.clock))
            check(isinstance(e, sm.SarvamServiceError) and KEY not in str(e),
                  "unreachable: SarvamServiceError, key redacted")

            # ── terminal states, timeouts, output shape ──────────────────────
            fk = Fake(final="failed")
            check(isinstance(attempt(lambda: run(fk)), sm.SarvamServiceError),
                  "a failed job raises; never an empty document")
            fk = Fake(polls=10_000)
            e = attempt(lambda: run(fk, max_wait=60))
            check(isinstance(e, sm.SarvamServiceError) and "not terminal" in str(e)
                  and fk.t < 200, "polling is bounded by max_wait")
            fk = Fake(final="partially_completed")
            res = run(fk)
            check(not res.complete and "PARTIAL pages_failed=2" in res.markdown(),
                  "partially_completed: kept, marked PARTIAL, not complete")
            fk = Fake(zip_mds=2)
            check(isinstance(attempt(lambda: run(fk)), sm.SarvamBadResponse),
                  "a ZIP with two .md files is refused, not chosen between")
            fk = Fake(script={3: (200, b'{"method": "GET", "url": "http://storage.example/x"}')})
            check(isinstance(attempt(lambda: run(fk)), sm.SarvamBadResponse),
                  "a non-https download URL is refused")

            # ── CLI ──────────────────────────────────────────────────────────
            err = io.StringIO()
            with mock.patch.dict(os.environ, {ACK_ENV: ""}), \
                    mock.patch.object(sys, "stderr", err):
                rc = main([str(pdf)])
            check(rc == 2 and ACK_ENV in err.getvalue(), "CLI without the ACK exits 2 "
                  "and says why")
    check(not net.called, "no test reached the network")
    print(f"\n{ok}/{ok + fail} passed")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        _test()
    else:
        sys.exit(main(sys.argv[1:]))
