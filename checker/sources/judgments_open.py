#!/usr/bin/env python3
"""eCourts judgments from the AWS Open Data buckets. Keyless, LICENSED, never VERIFIED.

STEP 3a. Two CC-BY-4.0 datasets managed by Dattam Labs, read ANONYMOUSLY from S3 with no
credentials: `indian-supreme-court-judgments` and `indian-high-court-judgments`, both
ap-south-1. Their terms record is in `checker/sources/terms.py` (`aws_sc_judgments`,
`aws_hc_judgments`) and a connector refuses to load without it -- no record, no fetch.

## Three rules this file exists to hold

1. **Assert the bytes, never the status.** A judgment PDF is accepted only when its
   Content-Type is a PDF AND its first bytes are `%PDF`. S3 answers a missing key with an
   HTTP 404 *and an XML body*, and a wrong path returns that XML with the key echoed -- a 200
   of XML where a PDF was expected is the silent failure CLAUDE.md names. The real key layout
   was learned by listing the bucket, not guessed: `data/pdf/year=YYYY/<lang>/<path>_<LANG>.pdf`
   -- my first guess, `data/pdf/year=YYYY/<path>.pdf`, returned NoSuchKey XML.

2. **A transport failure is FAILED, never "not found".** A dropped connection or a non-200
   raises `FetchError`. An empty result would say "there is no such judgment" about a fetch
   that never completed, and an abstention built on that would be a verified product state
   resting on a fiction.

3. **A quoted judgment must byte-match the stored text.** `fetch` stores the document and its
   sha256; it makes no claim about the contents. `quote()` is the only path that produces a
   citable `Evidence`, and it refuses a span that is not present byte-for-byte in the stored
   text. Tier LICENSED: a judgment may support an answer and can never make one VERIFIED
   (`tiers.can_verify(LICENSED)` is False).

## No credentials, no SDK, no network in a test

Reads are plain anonymous HTTPS GETs against the bucket's REST endpoint -- no `boto3`, no
signing, no new dependency. The `transport` is INJECTED, so the gate drives this against
fixtures and never opens a socket; `--live` passes the real one. The metadata parquet needs a
reader (`pandas`+`pyarrow`); that reader is injected too, so the gate needs no engine, and the
`--live` path says plainly when the engine is absent rather than returning nothing.

Run:  PYTHONPATH=. python3 checker/sources/judgments_open.py           # fixtures, no network
      PYTHONPATH=. python3 checker/sources/judgments_open.py --live    # one real read each
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from checker.sources import terms
from checker.sources.base import FetchError, SourceError
from checker.sources.evidence import Evidence
from checker.sources.tiers import LICENSED

# source_id (terms record) -> bucket name.
BUCKETS = {
    "aws_sc_judgments": "indian-supreme-court-judgments",
    "aws_hc_judgments": "indian-high-court-judgments",
}
REGION = "ap-south-1"

# Languages carry an uppercase suffix in the key: english -> _EN.
_LANG_SUFFIX = {"english": "EN", "hindi": "HI"}


class MetadataEngineMissing(SourceError):
    """No parquet reader is installed. NOT an empty metadata result.

    Separate from "no rows": an empty metadata list would say the year holds no judgments,
    about a file we could not even open. The `--live` path reports this and carries on with
    the PDF check, because the PDF path needs no engine.
    """


class NotAPdf(FetchError):
    """The bytes are not a PDF. The soft-404: a 200 (or 404) of XML where a PDF was expected."""


@dataclass(frozen=True)
class Response:
    """What a transport returns. Status, declared type, and the bytes -- all three, because
    the whole point is to check the bytes against the declared type and not trust either
    alone."""
    status: int
    content_type: str
    body: bytes


@dataclass(frozen=True)
class StoredJudgment:
    """A fetched judgment PDF: proven to be a PDF, hashed, not yet quoted."""
    source_id: str
    key: str
    url: str
    sha256: str
    content_type: str
    byte_count: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _real_transport(url: str, *, timeout: float = 30.0) -> Response:
    """A plain anonymous HTTPS GET with full TLS verification. Used only by `--live`.

    No credentials and no signing: these buckets are public open data. TLS is verified
    through `checker/robots.ssl_context()` -- the same context the rest of the fetch path
    uses, so a certificate problem fails closed here as everywhere.
    """
    import urllib.request

    from checker.robots import ssl_context
    req = urllib.request.Request(
        url, headers={"User-Agent": "PlacedOn/1.0 (CC-BY-4.0 open judgments; "
                                    "attribution: Dattam Labs, eCourts)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
            return Response(r.status, r.headers.get("content-type", ""), r.read())
    except Exception as exc:  # noqa: BLE001  -- a transport failure is FAILED, re-raised below
        raise FetchError(f"{url}: transport failed ({type(exc).__name__}: "
                         f"{str(exc)[:160]})") from exc


def _default_metadata_reader(parquet_bytes: bytes) -> list[dict]:
    """Parse a metadata parquet into a list of row dicts, via pandas.

    pandas is already a dependency; the parquet ENGINE (pyarrow/fastparquet) may not be
    installed, and when it is not this raises `MetadataEngineMissing` with the reason rather
    than returning nothing. Injected elsewhere, so the gate never reaches this.
    """
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - pandas is present in this repo
        raise MetadataEngineMissing(f"pandas is not installed: {exc}") from exc
    try:
        frame = pd.read_parquet(io.BytesIO(parquet_bytes))
    except Exception as exc:  # noqa: BLE001  -- usually a missing parquet engine
        raise MetadataEngineMissing(
            f"could not read the metadata parquet ({type(exc).__name__}: "
            f"{str(exc)[:140]}). Install a parquet engine (pyarrow) for the metadata path; "
            f"the PDF path needs none") from exc
    return [dict(row) for row in frame.to_dict(orient="records")]


@dataclass
class OpenJudgments:
    """One eCourts judgment bucket. Keyless, LICENSED.

    `transport` and `metadata_reader` are injected so the gate runs offline against fixtures.
    The default transport is a real anonymous GET; the default reader uses pandas.
    """
    source_id: str
    transport: Callable[[str], Response] = _real_transport
    metadata_reader: Callable[[bytes], list[dict]] = _default_metadata_reader

    def __post_init__(self) -> None:
        if self.source_id not in BUCKETS:
            raise SourceError(
                f"{self.source_id!r} is not an open-judgments source; one of "
                f"{sorted(BUCKETS)}")
        # No record, no fetch. `may_fetch` also confirms robots permit (the bucket virtual
        # host 404s /robots.txt, an RFC 9309 allowance) and that no clause is PROHIBITED.
        ok, why = terms.may_fetch(self.source_id)
        if not ok:
            raise SourceError(f"{self.source_id}: refused by its terms record ({why})")
        self.bucket = BUCKETS[self.source_id]
        self.tier = LICENSED

    def _url(self, key: str) -> str:
        return f"https://{self.bucket}.s3.{REGION}.amazonaws.com/{key}"

    def metadata(self, year: int, *, court: str = "", bench: str = "") -> list[dict]:
        """The structured metadata rows for one year. Parquet, parsed by the injected reader.

        The two datasets are NOT laid out alike, and assuming they were is exactly the kind
        of guess this file refuses -- learned by listing both buckets:
          - Supreme Court: `metadata/parquet/year=YYYY/metadata.parquet` (flat).
          - High Court:    `metadata/parquet/year=YYYY/court=<code>/bench=<name>/metadata.parquet`
            -- partitioned by court and bench, so `court` and `bench` are required for it.

        A non-200 is a transport failure, raised -- never flattened to an empty year, which
        would claim the court decided nothing that year.
        """
        if self.source_id == "aws_hc_judgments" and not (court and bench):
            raise SourceError(
                "aws_hc_judgments metadata is partitioned by court and bench "
                "(metadata/parquet/year=YYYY/court=<code>/bench=<name>/metadata.parquet); "
                "pass court= and bench=. The Supreme Court set is flat and needs neither.")
        if court and bench:
            key = (f"metadata/parquet/year={int(year)}/court={court}/bench={bench}/"
                   f"metadata.parquet")
        else:
            key = f"metadata/parquet/year={int(year)}/metadata.parquet"
        resp = self.transport(self._url(key))
        if resp.status != 200:
            raise FetchError(
                f"{self.source_id}: metadata for {year} returned HTTP {resp.status}, not "
                f"200. A non-200 is a transport failure, not an empty year")
        return self.metadata_reader(resp.body)

    def fetch(self, path: str, *, year: int, lang: str = "english") -> StoredJudgment:
        """Fetch one judgment PDF and store it. Asserts it is a PDF; makes no claim about it.

        The key layout is `data/pdf/year=YYYY/<lang>/<path>_<LANG>.pdf`, learned by listing
        the bucket. The content-type AND the `%PDF` magic bytes are both checked -- a 200 of
        XML (S3's error body) passes neither, and is raised as `NotAPdf`, never read as "no
        such judgment".
        """
        suffix = _LANG_SUFFIX.get(lang.lower())
        if suffix is None:
            raise SourceError(f"{self.source_id}: unknown language {lang!r}; "
                              f"one of {sorted(_LANG_SUFFIX)}")
        key = f"data/pdf/year={int(year)}/{lang.lower()}/{path}_{suffix}.pdf"
        url = self._url(key)
        resp = self.transport(url)
        if resp.status != 200:
            raise FetchError(f"{self.source_id}: {key} returned HTTP {resp.status}")
        ct = (resp.content_type or "").lower()
        if "pdf" not in ct or resp.body[:4] != b"%PDF":
            raise NotAPdf(
                f"{self.source_id}: {key} is not a PDF (content-type {ct!r}, first bytes "
                f"{resp.body[:8]!r}). S3 serves a missing or wrong key as an XML error body "
                f"with HTTP 200/404; a judgment is accepted only on its %PDF bytes, never on "
                f"the status code alone")
        return StoredJudgment(
            source_id=self.source_id, key=key, url=url,
            sha256=hashlib.sha256(resp.body).hexdigest(),
            content_type=resp.content_type, byte_count=len(resp.body))

    def quote(self, stored: StoredJudgment, span: str, *, document_text: str) -> Evidence:
        """A citable Evidence for one span -- ONLY if it byte-matches the stored text.

        `document_text` is the text extracted from the stored PDF (by the caller, through the
        repository's PDF text path). The span must appear in it verbatim; a span that does not
        is refused, because a quote that is not in the document is the one thing a legal
        citation may never be. The sha256 ties the quote to the exact bytes fetched.
        """
        if not span.strip():
            raise SourceError(f"{self.source_id}: an empty span is not a quote")
        if span not in document_text:
            raise SourceError(
                f"{self.source_id}: the span is not present byte-for-byte in the stored "
                f"judgment {stored.key} (sha256 {stored.sha256[:12]}). A quote that is not "
                f"in the document is refused, not approximated")
        return Evidence(
            tier=LICENSED, source=self.source_id, url=stored.url, doc_id=stored.key,
            fetched_at=_utc_now(), sha256=stored.sha256, quoted_span=span,
            # The terms' own words, which `evidence.Evidence` requires to match exactly for a
            # LICENSED row. The concrete credit (Dattam Labs, the CC-BY link) is in the terms
            # record's note and is what a UI renders alongside.
            attribution=terms.attribution_for(self.source_id))


def _live_smoke() -> int:
    """One real anonymous read per bucket. Prints status, shape and sha256. No key exists.

    NOT in the gate. Proves the prototype connects to the live datasets; the metadata path
    needs a parquet engine and says so if absent, while the PDF path proves the connection
    either way.
    """
    print("judgments_open --live (anonymous, no credentials)\n")
    rc = 0

    # Supreme Court: metadata (engine-aware) + one real PDF, both proven live.
    print("=== aws_sc_judgments (indian-supreme-court-judgments) ===")
    try:
        sc = OpenJudgments("aws_sc_judgments")
        try:
            rows = sc.metadata(1950)
            print(f"  metadata year=1950: {len(rows)} rows; columns="
                  f"{sorted(rows[0])[:8] if rows else '(none)'}")
        except MetadataEngineMissing as e:
            print(f"  metadata: engine missing ({str(e)[:64]}...) -- PDF path still proven")
        except FetchError as e:
            print(f"  metadata: FAILED ({str(e)[:88]})"); rc = 1
        stored = sc.fetch("1950_1_15_25", year=1950)
        print(f"  PDF {stored.key}: {stored.content_type}, {stored.byte_count} bytes, "
              f"sha256 {stored.sha256[:16]}...")
    except (SourceError, FetchError) as e:
        print(f"  FAILED: {str(e)[:100]}"); rc = 1
    print()

    # High Court: prove it LOADS (terms gate) and state the structural difference rather than
    # fetch a key the SC layout would wrongly build. HC metadata is court/bench-partitioned.
    print("=== aws_hc_judgments (indian-high-court-judgments) ===")
    try:
        hc = OpenJudgments("aws_hc_judgments")
        print(f"  loads: terms permit, tier {hc.tier}")
        try:
            hc.metadata(1950)
        except SourceError as e:
            print(f"  metadata: correctly requires court+bench "
                  f"({str(e)[:70]}...)")
    except SourceError as e:
        print(f"  FAILED to load: {str(e)[:100]}"); rc = 1
    print()

    print("spent: Rs 0.00 (keyless open data)")
    return rc


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("judgments_open")

    PDF = b"%PDF-1.7\n...a judgment with the words annual general meeting in it...\n%%EOF"
    XML_404 = (b"<?xml version=\"1.0\"?><Error><Code>NoSuchKey</Code>"
               b"<Message>The specified key does not exist.</Message></Error>")
    META_ROWS = [{"path": "1950_1_15_25", "citation_year": 1950, "nc_display": "1950INSC1"},
                 {"path": "1950_1_25_29", "citation_year": 1950, "nc_display": "1950INSC2"}]

    seen: list[str] = []

    def transport(url: str) -> Response:
        seen.append(url)
        if url.endswith("metadata.parquet"):
            return Response(200, "application/octet-stream", b"PAR1-fake-bytes")
        if url.endswith("1950_1_15_25_EN.pdf"):
            return Response(200, "application/pdf", PDF)
        if url.endswith("missing_EN.pdf"):
            # S3's real behaviour: a wrong key is a 200/404 of XML, not a 404 of nothing.
            return Response(404, "application/xml", XML_404)
        if url.endswith("softfour_EN.pdf"):
            return Response(200, "application/xml", XML_404)  # the dangerous one: 200 of XML
        raise ConnectionError("the host closed the connection")

    j = OpenJudgments("aws_sc_judgments", transport=transport,
                      metadata_reader=lambda b: META_ROWS)

    # ── keyless, LICENSED, and loaded only through its terms record ──────────
    check(j.tier == LICENSED, f"the tier is LICENSED ({j.tier})")
    from checker.sources.tiers import can_verify
    check(not can_verify(LICENSED),
          "a judgment can never make an answer VERIFIED -- enforced by tiers.can_verify")
    check(j.bucket == "indian-supreme-court-judgments", f"bound to the right bucket "
                                                        f"({j.bucket})")

    # ── metadata: parsed by the injected reader; a non-200 is FAILED ────────
    rows = j.metadata(1950)
    check(rows == META_ROWS, f"metadata parses via the injected reader ({len(rows)} rows)")
    check(any("metadata/parquet/year=1950" in u for u in seen),
          "...from the real parquet key layout")

    def bad_transport(url: str) -> Response:
        return Response(503, "text/html", b"<h1>503</h1>")
    jb = OpenJudgments("aws_sc_judgments", transport=bad_transport,
                       metadata_reader=lambda b: META_ROWS)
    try:
        jb.metadata(1950)
        check(False, "a 503 on metadata must raise, not return an empty year")
    except FetchError as e:
        check("not an empty year" in str(e),
              "a non-200 metadata is FAILED, never an empty year")

    # ── fetch asserts %PDF bytes, not the status code ───────────────────────
    stored = j.fetch("1950_1_15_25", year=1950)
    check(stored.sha256 == hashlib.sha256(PDF).hexdigest(),
          "a real PDF is stored with its sha256")
    check(stored.key == "data/pdf/year=1950/english/1950_1_15_25_EN.pdf",
          f"...at the real key layout learned from the bucket ({stored.key})")
    check(stored.byte_count == len(PDF), "...and its byte count")

    # the soft-404: 200 of XML where a PDF was expected. The failure this file exists for.
    try:
        j.fetch("softfour", year=1950)
        check(False, "a 200 of XML must be refused as not-a-PDF")
    except NotAPdf as e:
        check("never on the status code alone" in str(e),
              "a 200 of XML is NotAPdf -- the status said OK and the bytes said otherwise")
    # a real 404 (also XML) -> raised, never "no such judgment"
    try:
        j.fetch("missing", year=1950)
        check(False, "a 404 must raise")
    except FetchError:
        check(True, "a 404 is a transport failure, not an empty result")
    # a dropped connection -> FAILED
    try:
        j.fetch("1999_9_9_9", year=1999)
        check(False, "a dropped connection must raise")
    except (FetchError, ConnectionError):
        check(True, "a dropped connection is FAILED, never 'not found'")

    # ── a quote must byte-match the stored text ─────────────────────────────
    text = "In this matter the company must hold an annual general meeting every year."
    ev = j.quote(stored, "annual general meeting", document_text=text)
    check(ev.tier == LICENSED and ev.sha256 == stored.sha256,
          "a byte-matched quote yields a LICENSED Evidence tied to the stored sha256")
    check(ev.attribution == terms.attribution_for("aws_sc_judgments"),
          "...carrying the terms' own attribution words, which Evidence requires to match")
    check(not ev.can_verify, "...and it cannot verify")
    try:
        j.quote(stored, "a sentence that is not in the judgment", document_text=text)
        check(False, "a span absent from the text must be refused")
    except SourceError as e:
        check("not present byte-for-byte" in str(e),
              "a quote not in the document is refused, not approximated")
    try:
        j.quote(stored, "   ", document_text=text)
        check(False, "an empty span must be refused")
    except SourceError:
        check(True, "an empty span is not a quote")

    # ── the two datasets are NOT laid out alike ─────────────────────────────
    hc_seen: list[str] = []

    def hc_transport(url: str) -> Response:
        hc_seen.append(url)
        return Response(200, "application/octet-stream", b"PAR1")
    hc = OpenJudgments("aws_hc_judgments", transport=hc_transport,
                       metadata_reader=lambda b: META_ROWS)
    try:
        hc.metadata(1950)
        check(False, "HC metadata without court+bench must refuse")
    except SourceError as e:
        check("partitioned by court and bench" in str(e),
              "HC metadata requires court+bench -- assuming the SC flat layout is the guess "
              "this file refuses")
    hc.metadata(1950, court="19_16", bench="calcutta_original_side")
    check(any("court=19_16/bench=calcutta_original_side" in u for u in hc_seen),
          "...and with them, the real court/bench-partitioned key is built")
    # The SC connector stays flat and needs neither.
    check(any(u.endswith("year=1950/metadata.parquet") for u in seen),
          "the Supreme Court key is flat (year=YYYY/metadata.parquet), as its bucket is")

    # ── a source whose terms forbid does not load ───────────────────────────
    try:
        OpenJudgments("not_a_bucket", transport=transport)
        check(False, "an unknown source must refuse to load")
    except SourceError as e:
        check("not an open-judgments source" in str(e),
              "an unknown source refuses to load, naming the known ones")

    # ── no credentials, no SDK, no network in this module ───────────────────
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(
        __import__("checker.sources.judgments_open", fromlist=["x"])))
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    check("boto3" not in mods and "botocore" not in mods,
          f"no AWS SDK: reads are unsigned anonymous GETs, so no credentials can be used "
          f"({sorted(m for m in mods if m)})")
    # Every real GET goes through the injected transport; the only urllib import is inside
    # `_real_transport`, which the gate never calls.
    check(all(not u.startswith("http") or ".amazonaws.com/" in u for u in seen),
          "every fetch addressed the bucket endpoint and nothing else")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--live" in sys.argv:
        raise SystemExit(_live_smoke())
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
