"""Azure AI Document Intelligence v4 — layout OCR for Indian legal documents.

Primary OCR path: free 500 pages/month on Azure for Students. Extracts text,
tables, and reading order from scanned PDFs including Hindi/English bilingual
Gazette notifications.

Fallback: Mistral OCR 4.1 on the same Azure Foundry resource. It runs only when
Azure DI raises (HTTP error, analysis failure, or timeout) and only if
`MISTRAL_AZURE_*` is configured. Mistral's OCR deployment takes page IMAGES, so
the PDF is rasterised first with `pypdfium2` + Pillow (dev-only, see
requirements-dev.txt). If neither is installed the fallback refuses with a
message naming the missing dependency rather than returning empty text.

Uses the same endpoint and key as azure_model.py (placedon-law-eval, AIServices).
The prebuilt-layout model handles any document without training.

Run: PYTHONPATH=. python3 checker/azure_doc_intel.py --test
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from checker.anthropic_model import ModelUnavailable
from checker.env import load as _load_env

_load_env()

MODEL = "prebuilt-layout"
API_VERSION = "2024-11-30"
POLL_INTERVAL_S = 3
MAX_WAIT_S = 120
TIMEOUT_S = 30

# Mistral OCR is a chat deployment that transcribes an image; it is not asked to
# interpret, summarise, or format. The instruction keeps the output usable as a
# drop-in for Azure DI's `content` field.
OCR_PROMPT = (
    "Transcribe every character on this page exactly as printed, preserving "
    "reading order and line breaks. Output only the transcription, with no "
    "commentary, markdown, or page markers."
)


def available() -> bool:
    return bool(os.getenv("AZURE_AI_ENDPOINT") and os.getenv("AZURE_AI_API_KEY"))


def _endpoint() -> str:
    ep = os.getenv("AZURE_AI_ENDPOINT", "").rstrip("/")
    if not ep:
        raise ModelUnavailable("AZURE_AI_ENDPOINT is not set")
    return ep


def _key() -> str:
    k = os.getenv("AZURE_AI_API_KEY", "")
    if not k:
        raise ModelUnavailable("AZURE_AI_API_KEY is not set")
    return k


def _ssl_context():
    from checker.robots import ssl_context
    return ssl_context()


def _request(method: str, url: str, body: bytes | None = None,
             content_type: str = "application/json") -> urllib.request.Request:
    headers = {
        "Ocp-Apim-Subscription-Key": _key(),
        "Content-Type": content_type,
    }
    return urllib.request.Request(url, data=body, headers=headers, method=method)


def _open(req: urllib.request.Request, timeout: int = TIMEOUT_S):
    ctx = _ssl_context()
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise ModelUnavailable(f"Azure DocIntel HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise ModelUnavailable(f"Azure DocIntel connection error: {e}") from None


def submit_pdf(path: str | Path) -> str:
    """Submit a PDF for layout analysis. Returns the operation URL to poll."""
    pdf_bytes = Path(path).read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    url = f"{_endpoint()}/documentintelligence/documentModels/{MODEL}:analyze?api-version={API_VERSION}"
    body = json.dumps({"base64Source": b64}).encode()
    req = _request("POST", url, body)
    resp = _open(req, timeout=60)
    op_url = resp.headers.get("Operation-Location") or resp.headers.get("operation-location")
    if not op_url:
        raise ModelUnavailable("no Operation-Location header in 202 response")
    return op_url


def poll_result(op_url: str, *, max_wait: float = MAX_WAIT_S) -> dict:
    """Poll until the analysis completes or times out."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        req = _request("GET", op_url)
        resp = _open(req)
        data = json.loads(resp.read())
        status = data.get("status", "")
        if status == "succeeded":
            return data.get("analyzeResult", {})
        if status == "failed":
            raise ModelUnavailable(f"Azure DocIntel analysis failed: {data}")
        time.sleep(POLL_INTERVAL_S)
    raise ModelUnavailable(f"Azure DocIntel timed out after {max_wait}s")


def extract_text(result: dict) -> str:
    """The full document text from an analyzeResult."""
    return result.get("content", "")


def extract_tables(result: dict) -> list[dict]:
    """Tables as list of {rowCount, columnCount, cells: [{content, rowIndex, columnIndex}]}."""
    tables = []
    for t in result.get("tables", []):
        tables.append({
            "rowCount": t.get("rowCount", 0),
            "columnCount": t.get("columnCount", 0),
            "cells": [{"content": c.get("content", ""),
                        "rowIndex": c.get("rowIndex", 0),
                        "columnIndex": c.get("columnIndex", 0)}
                       for c in t.get("cells", [])],
        })
    return tables


def _render_pages(path: str | Path, *, scale: float = 2.0) -> list[bytes]:
    """Rasterise each PDF page to PNG bytes for the Mistral OCR fallback.

    PyMuPDF is not used: AGPL section 13 would extend to this served backend
    (see checker/pdf_pages.py). pypdfium2 is BSD/Apache-2.0; Pillow is needed
    only to encode the bitmap as PNG. Both are dev-only.
    """
    try:
        import io

        import pypdfium2 as pdfium
        from PIL import Image  # noqa: F401  (required by .to_pil())
    except Exception as e:
        raise ModelUnavailable(
            "Mistral OCR fallback needs pypdfium2 and Pillow to rasterise a PDF "
            f"({e}); install requirements-dev.txt") from None

    try:
        doc = pdfium.PdfDocument(str(path))
        pages: list[bytes] = []
        for i in range(len(doc)):
            bitmap = doc[i].render(scale=scale)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            pages.append(buf.getvalue())
        return pages
    except ModelUnavailable:
        raise
    except Exception as e:
        raise ModelUnavailable(
            f"could not rasterise {path} for Mistral OCR: {e}") from None


def _mistral_digitise(path: str | Path) -> dict:
    """Mistral OCR 4.1 fallback: page image → transcription, page by page."""
    from checker import mistral_model

    pages = _render_pages(path)
    texts = [mistral_model.ocr(
        OCR_PROMPT, base64.b64encode(png).decode("ascii")) for png in pages]
    return {
        "text": "\n\n".join(t for t in texts if t),
        "pages": len(pages),
        "tables": [],
        "provider": "mistral_ocr",
        "model": mistral_model.OCR,
    }


def digitise(path: str | Path, *, max_wait: float = MAX_WAIT_S) -> dict:
    """Full pipeline: submit PDF → poll → return {text, pages, tables}.

    Azure DI is primary. On ModelUnavailable it falls back to Mistral OCR 4.1
    when that deployment is configured; a failure of both is reported as one
    error naming both causes, never as empty text.
    """
    try:
        op_url = submit_pdf(path)
        result = poll_result(op_url, max_wait=max_wait)
    except ModelUnavailable as azure_error:
        from checker import mistral_model
        if not mistral_model.available():
            raise
        try:
            return _mistral_digitise(path)
        except ModelUnavailable as mistral_error:
            raise ModelUnavailable(
                f"Azure DocIntel failed ({azure_error}); Mistral OCR fallback "
                f"also failed ({mistral_error})") from None

    return {
        "text": extract_text(result),
        "pages": len(result.get("pages", [])),
        "tables": extract_tables(result),
        "provider": "azure_doc_intel",
        "model": MODEL,
    }


# ── self-tests ──────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("azure_doc_intel")

    # ── availability ────────────────────────────────────────────────────
    held = {k: os.environ.pop(k, None) for k in ("AZURE_AI_ENDPOINT", "AZURE_AI_API_KEY")}
    try:
        check(not available(), "unavailable without env vars")
        os.environ["AZURE_AI_ENDPOINT"] = "https://test.cognitiveservices.azure.com/"
        os.environ["AZURE_AI_API_KEY"] = "test-key"
        check(available(), "available with both env vars")
    finally:
        for k, v in held.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    # ── extract_text ────────────────────────────────────────────────────
    mock_result = {"content": "Section 134 of the Companies Act", "pages": [{}], "tables": []}
    check(extract_text(mock_result) == "Section 134 of the Companies Act",
          "extract_text returns content")

    # ── extract_tables ──────────────────────────────────────────────────
    mock_with_table = {"tables": [{"rowCount": 2, "columnCount": 2,
                                    "cells": [{"content": "A", "rowIndex": 0, "columnIndex": 0}]}]}
    tables = extract_tables(mock_with_table)
    check(len(tables) == 1 and tables[0]["rowCount"] == 2, "extract_tables parses table")
    check(tables[0]["cells"][0]["content"] == "A", "table cell content extracted")

    # ── empty result ────────────────────────────────────────────────────
    check(extract_text({}) == "", "empty result returns empty string")
    check(extract_tables({}) == [], "empty result returns no tables")

    # ── Mistral OCR fallback (no network) ───────────────────────────────
    from unittest.mock import patch
    from checker import mistral_model as mm

    with patch.object(sys.modules[__name__], "submit_pdf",
                      side_effect=ModelUnavailable("azure down")), \
         patch.object(sys.modules[__name__], "_render_pages",
                      return_value=[b"png-1", b"png-2"]), \
         patch.object(mm, "available", return_value=True), \
         patch.object(mm, "ocr", return_value="Section 134 text") as ocr_mock:
        got = digitise("ignored.pdf")
    check(got["provider"] == "mistral_ocr", "fallback tags provider mistral_ocr")
    check(got["model"] == mm.OCR, "fallback names the OCR deployment")
    check(got["pages"] == 2, "fallback counts rendered pages")
    check(got["text"] == "Section 134 text\n\nSection 134 text",
          "fallback joins per-page transcriptions")
    check(ocr_mock.call_count == 2, "fallback calls OCR once per page")

    with patch.object(sys.modules[__name__], "submit_pdf",
                      side_effect=ModelUnavailable("azure down")), \
         patch.object(mm, "available", return_value=False):
        try:
            digitise("ignored.pdf")
            check(False, "unconfigured fallback re-raises the Azure error")
        except ModelUnavailable as e:
            check("azure down" in str(e),
                  "unconfigured fallback re-raises the Azure error")

    with patch.object(sys.modules[__name__], "submit_pdf",
                      side_effect=ModelUnavailable("azure down")), \
         patch.object(sys.modules[__name__], "_render_pages",
                      side_effect=ModelUnavailable("no renderer")), \
         patch.object(mm, "available", return_value=True):
        try:
            digitise("ignored.pdf")
            check(False, "both failures are reported as one error")
        except ModelUnavailable as e:
            check("azure down" in str(e) and "no renderer" in str(e),
                  "both failures are reported as one error")

    # ── live test (only if keys are set) ────────────────────────────────
    test_pdf = Path("corpus/sources/gsr880e_2025.pdf")
    if available() and test_pdf.exists():
        try:
            result = digitise(test_pdf)
            check(result["pages"] > 0, f"live: extracted {result['pages']} pages")
            check(len(result["text"]) > 100, f"live: got {len(result['text'])} chars")
            check("Gazette" in result["text"] or "राजपत्र" in result["text"],
                  "live: recognized Gazette/राजपत्र in bilingual PDF")
            check(result["provider"] == "azure_doc_intel", "provider tag correct")
        except ModelUnavailable as e:
            print(f"  [SKIP] live test: {e}")
    else:
        print("  [SKIP] live test (no keys or no test PDF)")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    if len(sys.argv) > 1:
        path = sys.argv[1]
        result = digitise(path)
        print(f"Pages: {result['pages']}")
        print(f"Tables: {len(result['tables'])}")
        print(result["text"][:1000])
    else:
        print(__doc__)
