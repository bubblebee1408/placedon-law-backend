"""Azure AI Document Intelligence v4 — layout OCR for Indian legal documents.

Primary OCR path: free 500 pages/month on Azure for Students. Extracts text,
tables, and reading order from scanned PDFs including Hindi/English bilingual
Gazette notifications.

Fallback: Mistral OCR 4.1 on the same Azure Foundry resource.

Uses the same endpoint and key as azure_model.py (placedon-law-eval, AIServices).
The prebuilt-layout model handles any document without training.

Run: PYTHONPATH=. python3 checker/azure_doc_intel.py --test
"""
from __future__ import annotations

import base64
import json
import os
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


def digitise(path: str | Path, *, max_wait: float = MAX_WAIT_S) -> dict:
    """Full pipeline: submit PDF → poll → return {text, pages, tables}."""
    op_url = submit_pdf(path)
    result = poll_result(op_url, max_wait=max_wait)
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
