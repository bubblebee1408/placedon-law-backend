"""Sarvam Document AI (Digitise): an OCR CANDIDATE for page images, behind a privacy guard.

Not on any serving path. `checker/router.py` lists Sarvam as a PAGE_IMAGE candidate,
never as preferred; the preference changes only after `scripts/bakeoff_indic.py`
wins on the same pages and metric as the incumbent's evidence.

## What was pinned, from which page, on which date

Fetched 2026-09-18 as raw markdown (`<url>.md`), not through a summariser. Earlier
research: docs/research/SARVAM_DOCUMENT_AI.md (14-09); every row below was re-read.

    S1  https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md
    S2  https://docs.sarvam.ai/api-reference/doc-ai/job/status.md
    S3  https://docs.sarvam.ai/api-reference/doc-ai/job/results.md
    S4  https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md
    S5  https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md
    S6  https://docs.sarvam.ai/api/platform/data-retention.md
    S7  https://docs.sarvam.ai/api/getting-started/pricing.md  and  https://www.sarvam.ai/api-pricing
    S8  https://www.sarvam.ai/privacy-policy  ("Updated on: July 29, 2026")

SOURCED:
- `POST https://api.sarvam.ai/doc-ai/v1/job/digitise`, multipart/form-data: exactly one
  of `file` (repeatable) or `upload_ids`; `language` (BCP-47), `output_format`,
  `content_type`, `model`. 201 -> `{job_id, status, run_id}` (S1). Header
  `api-subscription-key` (S1).
- `output_format` is `html` (default), `md` or `json`; `"markdown"` returns 400 (S4).
- Async only: poll `GET /doc-ai/v1/job/{job_id}/status` -> `{job_id, status, pipeline,
  usage: {pages_total, pages_processed, pages_succeeded, pages_failed}, created_at,
  updated_at}` (S2). Terminal: completed, partially_completed ("some pages succeeded,
  some failed"), failed, rejected; non-terminal pending, running (S4).
- `GET /doc-ai/v1/job/{job_id}/results` -> digitise: `{type, documents: [{file_name,
  pages: [{page_number, content}]}], job_id, status, usage}`; `content` is "in the
  requested output_format (HTML or Markdown)"; 409 before a terminal status (S3).
- 10 pages per PDF, 10 images per ZIP (ordered by filename), 200 MB per file,
  10 requests/minute on every plan; >10 pages -> 400 invalid_request_error; "Split
  larger documents into batches of 10 pages or fewer" (S4, S5).
- Errors are problem+json: `{type, title, status, detail, instance, errors}` (S1);
  400, 402/403 billing, 404, 409, 413, 422, 429, 503 (S4).
- 23 language codes (S4) -- `LANGUAGES` below is copied from that table.
- Digitisation Rs 0.50 per page (S7, both pages agree).
- Retention: "Until an Owner sets a retention period, your workspace's data is retained
  indefinitely"; 0-day is supported for "Model APIs"; the "Doc Agents" override is "Not
  there yet" (S6).
- Training: "Default Policy: Opt-In -- We use Your content (including inputs, uploads
  ...) to train, fine-tune, and/or improve our AI models unless you explicitly opt-out"
  (S8, re-read 2026-09-18; unchanged since the 14-09 research).

UNVERIFIED:
- Accepted values of `content_type` and `model` (S1 lists neither) -- so neither is sent.
- Whether the Document AI API is covered by the "Model APIs" retention override (S6).
- Whether billing counts pages submitted or pages succeeded -- cost is an ESTIMATE on
  pages submitted, the conservative reading.
- How AI-written image/chart descriptions (docs/research/SARVAM_DOCUMENT_AI.md D7)
  appear inside `content`. Until seen live, `content` is kept raw beside the derived
  `text`, and nothing here claims the text is only what the page says.
- Whether status polls count against the 10 req/min limit. Every request is paced as
  if they do.

## What the LIVE API returned (first call, 19-09-2026) -- it is not the documented shape

One Digitise job on page 1 of the public G.S.R. 880(E) Gazette PDF (language en-IN,
output_format html), recorded by scripts/smoke_adapters.py and stored verbatim as
checker/fixtures/vendor_docs/sarvam_digitise_results_LIVE_2026-09-19.json:

- create and status matched S1/S2, plus an undocumented `$schema` field; the job was
  `completed` at the first poll, `usage` also carries `pages_discarded`.
- results came back `Content-Encoding: gzip` although no Accept-Encoding was sent.
  urllib does not decode that, so the first call was refused as non-JSON; `_call`
  now decodes gzip (by header, or by magic bytes) and refuses a body that claims gzip
  but is not.
- results differ from S3: `documents[].filename` (S3: `file_name`), plus `page_count`
  and `status`; each page is `{page_num, image_width, image_height, blocks}` -- S3's
  `page_number` and `content` are ABSENT. Text arrives as `blocks[{block_id,
  layout_tag, reading_order, coordinates{x1,y1,x2,y2}, bbox_norm, text}]`.
  `parse_digitise_results` accepts both shapes, each validated; the page text is the
  blocks in reading order, and the blocks are kept (tag + box) for page-anchored spans.
- Whether `output_format=md` changes that shape is UNVERIFIED (one job, html only).
- The page is bilingual; with language en-IN the Hindi was read too. The emblem came
  back as a `header` block holding the printed motto, not as an image description.
  Blocks tagged image/photograph/chart/diagram/figure are nonetheless quarantined as
  `model_written` and never enter `text` (INFERRED rule: which tags carry
  AI-written descriptions is UNVERIFIED).

## The privacy guard (why it is a check, not a comment)

Because of S8's default, a document sent here may train Sarvam's models. So
`privacy_check()` runs before a single byte is read for upload, and refuses unless:

1. the file is PUBLIC: its real path (symlinks resolved) is under `corpus/sources/` or
   `corpus/testdocs/`, it is tracked at HEAD, and its bytes are the committed blob
   (a tracked path whose working copy was swapped for a private file is refused); or
2. the `.env` FILE -- not the process environment -- carries
   `SARVAM_TRAINING_OPT_OUT=confirmed`, a line only the founder writes after opting out
   in Sarvam's dashboard. Reading the file rather than `os.environ` means an `export`
   in some shell cannot stand in for the founder's attestation.

## Splitting, never truncating

A PDF over 10 pages is split into <= 10-page PDFs (pypdf, already declared in
requirements-dev.txt for offline tooling and imported lazily here), each chunk is
re-read to confirm its page count, and results are mapped back to the original page
numbers. A caller who wants fewer pages asks for them with `page_range`, and the
result records the range asked for. Nothing is dropped silently.

## Fail closed

- No `SARVAM_API_KEY` -> `SarvamUnavailable`.
- HTTP error, timeout, a failed or rejected job, a job that never reaches a terminal
  state -> `SarvamServiceError`. Never an empty document, never an abstention.
- `partially_completed` -> the failed pages come back as `FAILED` pages, and the
  result says it is not complete. A page the vendor calls succeeded but returns no
  text for is `EMPTY`, not a blank page.
- A response off the documented shape -> `SarvamBadResponse`.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from checker.anthropic_model import ModelRefused, ModelUnavailable
from checker.env import DEFAULT as _ENV_FILE
from checker.env import load as _load_env

_load_env()

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.sarvam.ai/doc-ai/v1"
MODEL = "sarvam-vision"          # S5's model ID; not sent (S1 lists no accepted values)

MAX_PAGES_PER_JOB = 10
MAX_FILE_BYTES = 200 * 1024 * 1024
PRICE_INR_PER_PAGE = 0.50
OUTPUT_FORMATS = ("html", "md")   # json: results `content` is documented as HTML or MD only
TERMINAL = ("completed", "partially_completed", "failed", "rejected")
NON_TERMINAL = ("pending", "running")
LANGUAGES = ("hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN", "kn-IN", "ml-IN",
             "od-IN", "pa-IN", "as-IN", "brx-IN", "doi-IN", "ks-IN", "kok-IN", "mai-IN",
             "mni-IN", "ne-IN", "sa-IN", "sat-IN", "sd-IN", "ur-IN", "en-IN")

# 10 requests/minute on every plan (S4). 6 s is the average allowance; 6.5 s leaves
# a margin, and every request -- submit, poll, fetch -- is spaced by it.
MIN_GAP_S = 6.5
MAX_WAIT_S = 300
TIMEOUT_S = 120

PUBLIC_ROOTS = (ROOT / "corpus" / "sources", ROOT / "corpus" / "testdocs")
OPT_OUT_NAME = "SARVAM_TRAINING_OPT_OUT"
OPT_OUT_VALUE = "confirmed"
PUBLIC = "PUBLIC_CORPUS"
OPTED_OUT = "TRAINING_OPT_OUT_CONFIRMED"

_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,127}")
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class SarvamError(ModelUnavailable):
    """Base for every Sarvam refusal; a ModelUnavailable, so existing handling applies."""


class SarvamUnavailable(SarvamError):
    """No key, no splitter, or no way to authenticate the endpoint."""


class SarvamPrivacyRefused(SarvamError):
    """The document is not public and the training opt-out is not confirmed."""


class SarvamServiceError(SarvamError):
    """The call or the job failed. Never an empty document, never an abstention."""


class SarvamBadResponse(ModelRefused):
    """The response does not have the documented shape. Refused, not repaired."""


@dataclass(frozen=True)
class Clearance:
    basis: str               # PUBLIC or OPTED_OUT
    path: str
    blob: str | None = None  # the committed blob id, for a PUBLIC file


@dataclass(frozen=True)
class Part:
    filename: str
    content_type: str
    first_page: int
    n_pages: int
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    status: str
    pages_total: int | None = None
    pages_processed: int | None = None
    pages_succeeded: int | None = None
    pages_failed: int | None = None


@dataclass(frozen=True)
class Block:
    """One layout block of the LIVE results shape (see the 19-09 note above)."""
    block_id: str
    tag: str
    order: int
    text: str
    bbox: tuple[float, ...] | None


@dataclass(frozen=True)
class PageText:
    page: int                # page number in the ORIGINAL document
    status: str              # READ | EMPTY | FAILED
    content: str | None      # the documented shape's `content`, verbatim (None for blocks)
    text: str | None         # plain text: from content, or from the blocks in reading order
    blocks: tuple[Block, ...] = ()
    model_written: tuple[str, ...] = ()   # quarantined: never part of `text`


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    run_id: str | None
    status: str
    first_page: int
    n_pages: int
    usage: JobStatus


@dataclass(frozen=True)
class DigitiseResult:
    source: str
    basis: str
    language: str
    output_format: str
    pages_requested: tuple[int, int]
    pages: tuple[PageText, ...]
    jobs: tuple[JobRecord, ...]
    est_cost_inr: float

    @property
    def complete(self) -> bool:
        return all(p.status == "READ" for p in self.pages)


def available() -> bool:
    return bool((os.getenv("SARVAM_API_KEY") or "").strip())


def _key() -> str:
    # Stripped, as in voyage_model: a whitespace-only key from a shell export otherwise
    # read as present and produced a whitespace header (D6 verifier, finding 1).
    k = (os.getenv("SARVAM_API_KEY") or "").strip()
    if not k:
        raise SarvamUnavailable(
            "SARVAM_API_KEY is not set. This refuses rather than return an empty "
            "document, because a blank reading is indistinguishable from a blank page.")
    return k


def _redact(text: str, key: str | None) -> str:
    return text.replace(key, "<redacted>") if key else text


# ── the privacy guard ─────────────────────────────────────────────────────────
def _env_file_value(name: str, path: Path | None = None) -> str | None:
    """`name`'s value in the .env FILE, parsed exactly as checker.env.load parses it
    (first occurrence, quotes stripped) -- but never from os.environ."""
    p = path or _ENV_FILE
    if not p.is_file():
        return None
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def _git_run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                       text=True, timeout=30)
    return r.returncode, r.stdout.strip()


def privacy_check(path, *, env_path: Path | None = None, _git=None) -> Clearance:
    """Allowed only for a held public file, or after the founder's .env opt-out line."""
    how = (f"Allowed only for a PUBLIC file this repo holds under corpus/sources/ or "
           f"corpus/testdocs/ (tracked at HEAD, bytes unchanged), or once the .env file "
           f"carries {OPT_OUT_NAME}={OPT_OUT_VALUE} -- a line only the founder writes, "
           f"after opting out of training in Sarvam's dashboard.")
    p = Path(path)
    if not p.is_file():
        raise SarvamPrivacyRefused(f"{p} is not a regular file. {how}")
    if _env_file_value(OPT_OUT_NAME, env_path) == OPT_OUT_VALUE:
        return Clearance(OPTED_OUT, str(p))
    real = p.resolve(strict=True)
    root = next((r.resolve() for r in PUBLIC_ROOTS if real.is_relative_to(r.resolve())), None)
    if root is None:
        raise SarvamPrivacyRefused(
            f"{p.name} is not under a public corpus directory, and Sarvam trains on "
            f"uploads by default (privacy policy, 29-07-2026). {how}")
    rel = real.relative_to(ROOT.resolve()).as_posix()
    git = _git or _git_run
    try:
        rc, head_blob = git(["rev-parse", "--verify", "--quiet", f"HEAD:{rel}"])
        rc2, work_blob = git(["hash-object", "--", str(real)])
    except (OSError, subprocess.SubprocessError) as e:
        raise SarvamPrivacyRefused(
            f"cannot confirm {rel} is a file the repo holds ({type(e).__name__}). {how}") from None
    if rc != 0 or not head_blob:
        raise SarvamPrivacyRefused(f"{rel} is not a file the repo holds at HEAD. {how}")
    if rc2 != 0 or work_blob != head_blob:
        raise SarvamPrivacyRefused(
            f"{rel}: the bytes on disk differ from the committed public file. {how}")
    return Clearance(PUBLIC, rel, head_blob)


# ── splitting ─────────────────────────────────────────────────────────────────
def plan_chunks(n_pages: int, max_pages: int = MAX_PAGES_PER_JOB) -> tuple[tuple[int, int], ...]:
    """1-based inclusive page ranges covering 1..n_pages, each <= max_pages."""
    if n_pages < 1 or max_pages < 1:
        raise ValueError(f"cannot plan {n_pages} pages in chunks of {max_pages}")
    return tuple((a, min(a + max_pages - 1, n_pages))
                 for a in range(1, n_pages + 1, max_pages))


def _check_size(part: Part) -> Part:
    if len(part.data) > MAX_FILE_BYTES:
        raise ValueError(f"{part.filename} is {len(part.data)} bytes, over the documented "
                         f"{MAX_FILE_BYTES}; refused rather than truncated")
    return part


def _pdf_parts(data: bytes, page_range: tuple[int, int] | None) -> list[Part]:
    try:
        import pypdf
    except ImportError as e:
        raise SarvamUnavailable(
            f"pypdf (requirements-dev.txt) is needed to split PDFs over "
            f"{MAX_PAGES_PER_JOB} pages: {e}") from None
    reader = pypdf.PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("an encrypted PDF is refused (the API rejects password-protected files)")
    n = len(reader.pages)
    lo, hi = page_range or (1, n)
    if not 1 <= lo <= hi <= n:
        raise ValueError(f"page_range {(lo, hi)} is outside this {n}-page PDF")
    if (lo, hi) == (1, n) and n <= MAX_PAGES_PER_JOB:
        return [_check_size(Part(f"pages-0001-{n:04d}.pdf", "application/pdf", 1, n, data))]
    parts = []
    for a, b in plan_chunks(hi - lo + 1):
        a, b = a + lo - 1, b + lo - 1
        writer = pypdf.PdfWriter()
        for i in range(a - 1, b):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        chunk = buf.getvalue()
        if len(pypdf.PdfReader(io.BytesIO(chunk)).pages) != b - a + 1:
            raise RuntimeError(f"splitting pages {a}-{b} produced the wrong page count")
        parts.append(_check_size(Part(f"pages-{a:04d}-{b:04d}.pdf", "application/pdf",
                                      a, b - a + 1, chunk)))
    return parts


def prepare_parts(path, *, page_range: tuple[int, int] | None = None) -> list[Part]:
    """Upload parts of <= 10 pages, covering exactly the pages asked for."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _pdf_parts(p.read_bytes(), page_range)
    if suffix in _IMAGE_TYPES:
        if page_range not in (None, (1, 1)):
            raise ValueError(f"an image has one page; page_range {page_range} is outside it")
        return [_check_size(Part(f"page-0001{suffix}", _IMAGE_TYPES[suffix], 1, 1,
                                 p.read_bytes()))]
    raise ValueError(f"{suffix or 'no extension'}: not a format the API lists "
                     f"(PDF, PNG, JPG); convert it first")


def image_zip_parts(paths) -> list[Part]:
    """Page images as flat ZIPs of <= 10, named so filename order is page order."""
    files = [Path(x) for x in paths]
    if not files:
        raise ValueError("no images")
    for f in files:
        if f.suffix.lower() not in _IMAGE_TYPES:
            raise ValueError(f"{f.name}: a ZIP may hold only PNG or JPG pages")
    parts = []
    for a, b in plan_chunks(len(files)):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for j, f in enumerate(files[a - 1:b], start=1):
                z.writestr(f"{j:04d}{f.suffix.lower()}", f.read_bytes())
        parts.append(_check_size(Part(f"pages-{a:04d}-{b:04d}.zip", "application/zip",
                                      a, b - a + 1, buf.getvalue())))
    return parts


# ── the wire ──────────────────────────────────────────────────────────────────
def build_multipart(fields, files, boundary: str) -> tuple[bytes, str]:
    sep = f"--{boundary}".encode()
    out = bytearray()
    for name, value in fields:
        out += sep + f'\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += str(value).encode("utf-8") + b"\r\n"
    for name, filename, ctype, data in files:
        if sep in data:
            raise ValueError("the multipart boundary occurs inside the file; choose another")
        out += sep + (f'\r\nContent-Disposition: form-data; name="{name}"; '
                      f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
        out += data + b"\r\n"
    out += sep + b"--\r\n"
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def build_request(method: str, path: str, key: str, body: bytes | None = None,
                  content_type: str | None = None) -> urllib.request.Request:
    if method not in ("GET", "POST") or not path.startswith("/job/"):
        raise ValueError(f"{method} {path!r} is not a pinned Document AI call")
    headers = {"api-subscription-key": key}
    if content_type:
        headers["Content-Type"] = content_type
    return urllib.request.Request(BASE + path, data=body, method=method, headers=headers)


def _problem(body: str) -> str:
    """The useful part of an RFC 7807 problem body (S1), or the raw text."""
    try:
        d = json.loads(body)
    except ValueError:
        return body
    if not isinstance(d, dict):
        return body
    bits = [str(d[k]) for k in ("title", "detail") if d.get(k)]
    errs = d.get("errors")
    if isinstance(errs, list):
        bits += [f"{e.get('location')}: {e.get('message')}" for e in errs if isinstance(e, dict)]
    return "; ".join(bits) or body


def _call(method: str, path: str, body: bytes | None, content_type: str | None,
          timeout: int = TIMEOUT_S) -> dict:
    """The real transport. Every failure raises; nothing becomes an empty document."""
    key = _key()
    req = build_request(method, path, key, body, content_type)
    from checker.robots import ssl_context
    ctx = ssl_context()
    if ctx is None:
        raise SarvamUnavailable("no CA trust store on this machine, so api.sarvam.ai "
                                "cannot be authenticated. Refusing to call it unverified.")
    service = "This is a service failure, not an empty document."
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            headers = getattr(r, "headers", None) or {}
            encoding = str(headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as e:
        detail = _redact(_problem(e.read().decode("utf-8", "replace")[:600]), key)[:300]
        kind = {429: "rate limited (10 req/min on every plan)",
                409: "results asked for before the job was terminal",
                402: "billing/entitlement", 403: "billing/entitlement",
                503: "billing unavailable"}.get(e.code, "error")
        raise SarvamServiceError(
            f"Sarvam HTTP {e.code} ({kind}) on {method} {path}: {detail}. {service}") from None
    except urllib.error.URLError as e:
        raise SarvamServiceError(f"Sarvam unreachable on {method} {path}: "
                                 f"{_redact(str(e.reason), key)}. {service}") from None
    except OSError as e:
        raise SarvamServiceError(f"Sarvam {method} {path} failed mid-flight "
                                 f"({type(e).__name__}: {_redact(str(e), key)[:120]}). "
                                 f"{service}") from None
    # Live 19-09: results arrive Content-Encoding: gzip, unasked. A JSON body can never
    # start with 0x1f, so the magic bytes are an unambiguous second signal.
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as e:
            raise SarvamBadResponse(
                f"{method} {path}: body claims gzip but does not decode ({e})") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SarvamBadResponse(f"{method} {path} returned 200 with a non-JSON body ({e})") from None


class _Pacer:
    """Spaces every request MIN_GAP_S after the previous one (10 req/min, S4)."""

    def __init__(self, transport, sleep, clock):
        self.transport, self.sleep, self.clock, self.last = transport, sleep, clock, None

    def __call__(self, method, path, body=None, content_type=None):
        if self.last is not None:
            wait = MIN_GAP_S - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        try:
            return self.transport(method, path, body, content_type)
        finally:
            self.last = self.clock()


# ── parsing, against the documented shapes ────────────────────────────────────
def _int_or_none(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def parse_created(data: object) -> tuple[str, str, str | None]:
    if not isinstance(data, dict):
        raise SarvamBadResponse("create-job response is not an object")
    jid, st, run = data.get("job_id"), data.get("status"), data.get("run_id")
    if not isinstance(jid, str) or not _JOB_ID.fullmatch(jid):
        raise SarvamBadResponse(f"create-job response has no usable job_id ({jid!r})")
    if not isinstance(st, str):
        raise SarvamBadResponse("create-job response has no status")
    return jid, st, run if isinstance(run, str) else None


def parse_status(data: object) -> JobStatus:
    if not isinstance(data, dict) or not isinstance(data.get("status"), str):
        raise SarvamBadResponse("status response has no status")
    u = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return JobStatus(str(data.get("job_id", "")), data["status"].lower(),
                     _int_or_none(u.get("pages_total")), _int_or_none(u.get("pages_processed")),
                     _int_or_none(u.get("pages_succeeded")), _int_or_none(u.get("pages_failed")))


class _Text(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "header", "footer", "ul", "ol", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)


def html_to_text(content: str) -> str:
    p = _Text()
    p.feed(content)
    p.close()
    lines = (re.sub(r"[ \t]+", " ", ln).strip() for ln in "".join(p.out).split("\n"))
    return "\n".join(ln for ln in lines if ln)


# Blocks whose text may be WRITTEN by the model (image/chart descriptions) rather than
# READ off the page. INFERRED from the documented section types; not yet observed live.
MODEL_WRITTEN_TAGS = ("image", "photograph", "chart", "diagram", "chart/diagram",
                      "chart-diagram", "figure")


def _blocks(raw: object, pn: int) -> tuple[tuple[Block, ...], tuple[str, ...]]:
    if not isinstance(raw, list):
        raise SarvamBadResponse(f"page {pn}: blocks is not a list")
    blocks = []
    for i, b in enumerate(raw):
        if not isinstance(b, dict) or not isinstance(b.get("text"), str):
            raise SarvamBadResponse(f"page {pn}: block {i} has no text")
        order = _int_or_none(b.get("reading_order"))
        if order is None:
            raise SarvamBadResponse(f"page {pn}: block {i} has no numeric reading_order")
        box = b.get("bbox_norm")
        bbox = (tuple(float(v) for v in box)
                if isinstance(box, list) and all(isinstance(v, (int, float)) for v in box)
                else None)
        blocks.append(Block(str(b.get("block_id", i)), str(b.get("layout_tag", "")),
                            order, b["text"], bbox))
    blocks.sort(key=lambda b: b.order)
    written = tuple(b.text for b in blocks if b.tag.lower() in MODEL_WRITTEN_TAGS)
    return tuple(blocks), written


def _page(pg: object, n_pages: int, output_format: str) -> tuple[int, dict]:
    """(page number, parsed) for either shape: documented {page_number, content} or
    live {page_num, blocks}. Anything else is refused."""
    if not isinstance(pg, dict):
        raise SarvamBadResponse("a page is not an object")
    pn = _int_or_none(pg.get("page_number", pg.get("page_num")))
    if pn is None or not 1 <= pn <= n_pages:
        raise SarvamBadResponse(f"page number {pn!r} is missing or outside 1..{n_pages}")
    if "content" in pg:
        content = pg["content"]
        if not isinstance(content, str):
            raise SarvamBadResponse(f"page {pn} content is not text")
        text = html_to_text(content) if output_format == "html" else content.strip()
        return pn, {"content": content, "text": text, "blocks": (), "written": ()}
    if "blocks" in pg:
        blocks, written = _blocks(pg["blocks"], pn)
        text = "\n".join(b.text.strip() for b in blocks
                         if b.tag.lower() not in MODEL_WRITTEN_TAGS and b.text.strip())
        return pn, {"content": None, "text": text, "blocks": blocks, "written": written}
    raise SarvamBadResponse(f"page {pn} has neither content nor blocks")


def parse_digitise_results(data: object, *, n_pages: int, first_page: int,
                           output_format: str) -> list[PageText]:
    """One PageText per page of the job, in original page numbers. Nothing dropped.

    Accepts the documented shape (S3) and the live shape seen 19-09 (see docstring)."""
    if not isinstance(data, dict) or data.get("type") != "digitise":
        raise SarvamBadResponse("results are not a digitise result")
    status = str(data.get("status", "")).lower()
    if status not in TERMINAL:
        raise SarvamBadResponse(f"results carry non-terminal status {status!r}")
    if status in ("failed", "rejected"):
        raise SarvamServiceError(f"job {data.get('job_id')} {status}; not an empty document")
    docs = data.get("documents")
    if not isinstance(docs, list) or len(docs) != 1 or not isinstance(docs[0], dict):
        raise SarvamBadResponse("expected exactly one document per job (one file is sent)")
    doc = docs[0]
    count = _int_or_none(doc.get("page_count"))
    if count is not None and count != n_pages:
        raise SarvamBadResponse(f"document page_count {count}, but {n_pages} pages were sent")
    doc_status = str(doc.get("status", status)).lower()
    if status == "completed" and doc_status != "completed":
        raise SarvamBadResponse(f"job completed but its document says {doc_status!r}")
    pages = doc.get("pages")
    if not isinstance(pages, list):
        raise SarvamBadResponse("the document has no pages list")
    got: dict[int, dict] = {}
    for pg in pages:
        pn, parsed = _page(pg, n_pages, output_format)
        if pn in got:
            raise SarvamBadResponse(f"page {pn} is repeated")
        got[pn] = parsed
    missing = [p for p in range(1, n_pages + 1) if p not in got]
    if status == "completed" and missing:
        raise SarvamBadResponse(f"'completed' but pages {missing} are absent")
    out = []
    for pn in range(1, n_pages + 1):
        g = got.get(pn)
        page = first_page + pn - 1
        if g is None or (not g["text"] and status == "partially_completed"):
            out.append(PageText(page, "FAILED", g and g["content"], None,
                                g["blocks"] if g else (), g["written"] if g else ()))
        else:
            out.append(PageText(page, "READ" if g["text"] else "EMPTY", g["content"],
                                g["text"], g["blocks"], g["written"]))
    return out


# ── the job ───────────────────────────────────────────────────────────────────
def _wait(job_id: str, call, clock, max_wait: float) -> JobStatus:
    start = clock()
    while True:
        st = parse_status(call("GET", f"/job/{job_id}/status"))
        if st.status in TERMINAL:
            return st
        if st.status not in NON_TERMINAL:
            raise SarvamBadResponse(f"job {job_id}: undocumented status {st.status!r}")
        if clock() - start > max_wait:
            raise SarvamServiceError(
                f"job {job_id} did not reach a terminal state within {max_wait} s "
                f"(last: {st.status}). Not an empty document; re-poll the job id.")


def _run_parts(parts: list[Part], *, source: str, basis: str, language: str,
               output_format: str, pages_requested: tuple[int, int], transport,
               sleep, clock, max_wait: float) -> DigitiseResult:
    call = _Pacer(transport, sleep, clock)
    pages: list[PageText] = []
    jobs: list[JobRecord] = []
    for part in parts:
        body, ctype = build_multipart(
            [("language", language), ("output_format", output_format)],
            [("file", part.filename, part.content_type, part.data)], uuid.uuid4().hex)
        job_id, _, run_id = parse_created(call("POST", "/job/digitise", body, ctype))
        st = _wait(job_id, call, clock, max_wait)
        if st.status in ("failed", "rejected"):
            raise SarvamServiceError(
                f"job {job_id} {st.status} (pages {part.first_page}-"
                f"{part.first_page + part.n_pages - 1}, pages_failed={st.pages_failed}). "
                f"A failed job is not an empty document.")
        pages += parse_digitise_results(call("GET", f"/job/{job_id}/results"),
                                        n_pages=part.n_pages, first_page=part.first_page,
                                        output_format=output_format)
        jobs.append(JobRecord(job_id, run_id, st.status, part.first_page, part.n_pages, st))
    lo, hi = pages_requested
    if [p.page for p in pages] != list(range(lo, hi + 1)):
        raise SarvamBadResponse("assembled pages do not match the pages requested")
    billed = sum(j.usage.pages_processed or j.n_pages for j in jobs)
    return DigitiseResult(source, basis, language, output_format, pages_requested,
                          tuple(pages), tuple(jobs), round(billed * PRICE_INR_PER_PAGE, 2))


def fetch_results(job_id: str, *, n_pages: int, first_page: int = 1,
                  output_format: str = "md", _transport=None) -> list[PageText]:
    """Re-read a job that already ran, with GETs only: no resubmission, no new spend.

    The status must already be terminal -- this neither waits nor guesses. It is the
    recovery path the service errors above point to ("re-poll the job id")."""
    if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
        raise ValueError(f"{job_id!r} is not a job id that is safe in a URL")
    if _transport is None:
        _key()
    call = _transport or _call
    st = parse_status(call("GET", f"/job/{job_id}/status", None, None))
    if st.status not in TERMINAL:
        raise SarvamServiceError(f"job {job_id} is not terminal yet ({st.status}); "
                                 f"re-poll later. Not an empty document.")
    if st.status in ("failed", "rejected"):
        raise SarvamServiceError(f"job {job_id} {st.status}; not an empty document")
    return parse_digitise_results(call("GET", f"/job/{job_id}/results", None, None),
                                  n_pages=n_pages, first_page=first_page,
                                  output_format=output_format)


def _validate(language: str, output_format: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"language {language!r} is not one of the 23 documented codes")
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"output_format must be one of {OUTPUT_FORMATS} "
                         f"('markdown' returns 400; results content is HTML or MD only)")


def digitise(path, *, language: str, output_format: str = "md",
             page_range: tuple[int, int] | None = None, env_path: Path | None = None,
             _transport=None, _sleep=None, _clock=None,
             max_wait: float = MAX_WAIT_S) -> DigitiseResult:
    """Digitise one document, split into <= 10-page jobs, after the privacy guard."""
    clearance = privacy_check(path, env_path=env_path)
    _validate(language, output_format)
    if _transport is None:
        _key()
    parts = prepare_parts(path, page_range=page_range)
    first = parts[0].first_page
    last = parts[-1].first_page + parts[-1].n_pages - 1
    return _run_parts(parts, source=clearance.path, basis=clearance.basis, language=language,
                      output_format=output_format, pages_requested=(first, last),
                      transport=_transport or _call, sleep=_sleep or time.sleep,
                      clock=_clock or time.monotonic, max_wait=max_wait)


def digitise_images(paths, *, language: str, output_format: str = "md",
                    env_path: Path | None = None, _transport=None, _sleep=None,
                    _clock=None, max_wait: float = MAX_WAIT_S) -> DigitiseResult:
    """Digitise page images, <= 10 per ZIP job; image i is page i of the result."""
    files = list(paths)
    bases = {privacy_check(f, env_path=env_path).basis for f in files}
    _validate(language, output_format)
    if _transport is None:
        _key()
    parts = image_zip_parts(files)
    return _run_parts(parts, source=f"{len(files)} images", basis="+".join(sorted(bases)),
                      language=language, output_format=output_format,
                      pages_requested=(1, len(files)), transport=_transport or _call,
                      sleep=_sleep or time.sleep, clock=_clock or time.monotonic,
                      max_wait=max_wait)


def _test() -> None:
    """The checks live in checker/sarvam_selftest.py only to keep each file under the
    repo's 800-line ceiling; this is still the suite scripts/run_tests.sh runs. No
    network: urlopen is replaced for the whole run and any call fails the run."""
    from checker.sarvam_selftest import run
    run()


if __name__ == "__main__":
    _test()
