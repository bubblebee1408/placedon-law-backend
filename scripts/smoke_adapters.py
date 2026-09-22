"""Live smoke test for the Voyage and Sarvam adapters -- the first real calls.

    python3 scripts/smoke_adapters.py --live     # makes the calls below
    python3 scripts/smoke_adapters.py            # says what it would do; no calls
    python3 scripts/smoke_adapters.py --test     # offline self-test, no network
    python3 scripts/smoke_adapters.py --live --sarvam-job <id>   # re-read one finished
                                                 # Sarvam job with GETs; nothing new sent

What it sends, and nothing else:

- Voyage: three short PUBLIC statute excerpts (Companies Act 2013 ss.173, 185, 188,
  first 400 characters each, from corpus/companies_act/ via section_index) embedded
  as documents; one query embedded; the same three excerpts reranked for that query.
  Three calls. Voyage trains on inputs unless the org opts out (docs/faq.md), which
  is why only public statute text is sent.
- Sarvam: page 1 of corpus/sources/gsr880e_2025.pdf (G.S.R. 880(E), a public Gazette
  notification the repo holds at HEAD) through Digitise, via the adapter's privacy
  guard. One job, about Rs 0.50 by the published per-page price.

For every call it records what the LIVE API returned against what the docs say:
top-level and per-item field names, statuses, the model echoed, usage, and any error.
It never prints or stores a key. The record goes to reports/smoke_adapters_<date>.json.
It refuses (exit 2) without both keys, and makes no call without --live.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import sarvam_model as sm  # noqa: E402
from checker import voyage_model as vm  # noqa: E402

SECTIONS = ("173", "185", "188")
EXCERPT_CHARS = 400
QUERY = "how many board meetings must a company hold in a year"
GAZETTE = ROOT / "corpus" / "sources" / "gsr880e_2025.pdf"
REFUSED = 2

# What the docs say each response carries (fetched 18-09; see each module's docstring).
DOCUMENTED = {
    "voyage/embeddings": {"top": {"object", "data", "model", "usage"},
                          "item": {"object", "embedding", "index"}},
    "voyage/rerank": {"top": {"object", "data", "model", "usage"},
                      "item": {"index", "relevance_score"}},
    "sarvam/POST /job/digitise": {"top": {"job_id", "status", "run_id"}},
    "sarvam/GET status": {"top": {"job_id", "status", "pipeline", "usage", "created_at",
                                  "updated_at"},
                          "usage": {"pages_total", "pages_processed", "pages_succeeded",
                                    "pages_failed"}},
    "sarvam/GET results": {"top": {"type", "documents", "job_id", "status", "usage"},
                           "document": {"file_name", "pages"},
                           "page": {"page_number", "content"}},
}


def compare(name: str, got: dict) -> dict:
    """Documented vs live field names, as sets. Extra fields are recorded, not fatal."""
    out = {}
    for level, want in DOCUMENTED[name].items():
        have = set(got.get(level) or ())
        out[level] = {"missing": sorted(want - have), "extra": sorted(have - want)}
    return out


def _keys(obj) -> list[str]:
    return sorted(obj) if isinstance(obj, dict) else []


def excerpts() -> list[str]:
    from checker import section_index as si
    from checker.corpus_retrieval import clean_html
    return [f"Section {n}. " + clean_html(si.section_by_number(n)["content"])[:EXCERPT_CHARS]
            for n in SECTIONS]


def voyage_smoke() -> dict:
    seen: list[dict] = []

    def recorder(endpoint, payload):
        data = vm._post(endpoint, payload)
        item = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
        seen.append({"endpoint": endpoint, "top": _keys(data), "item": _keys(item),
                     "model": data.get("model") if isinstance(data, dict) else None,
                     "usage": data.get("usage") if isinstance(data, dict) else None,
                     "object": data.get("object") if isinstance(data, dict) else None})
        return data

    docs = excerpts()
    rec: dict = {"sent": {"sections": list(SECTIONS), "chars_each": EXCERPT_CHARS,
                          "query": QUERY}, "calls": seen}
    try:
        dvecs, c1 = vm.embed(docs, input_type="document", _transport=recorder)
        qvec, c2 = vm.embed([QUERY], input_type="query", _transport=recorder)
        ranked, c3 = vm.rerank(QUERY, docs, _transport=recorder)
        rec["result"] = {
            "dims": sorted({len(v) for v in dvecs + qvec}),
            "norms": [round(sum(x * x for x in v) ** 0.5, 6) for v in dvecs + qvec],
            "rerank_order": [SECTIONS[i] for i, _ in ranked],
            "rerank_scores": [round(s, 6) for _, s in ranked],
            "tokens": [c1.total_tokens, c2.total_tokens, c3.total_tokens],
            "cost_inr_list": round(c1.cost_inr + c2.cost_inr + c3.cost_inr, 6)}
    except Exception as e:                           # noqa: BLE001 - recorded, not hidden
        rec["error"] = {"type": type(e).__name__, "message": str(e)[:500],
                        "where": traceback.format_exc(limit=3)[-600:]}
    for s in seen:
        name = f"voyage/{s['endpoint']}"
        s["vs_docs"] = compare(name, {"top": s["top"], "item": s["item"]})
    rec["call_count"] = len(seen)
    return rec


def sarvam_smoke(job_id: str | None = None) -> dict:
    seen: list[dict] = []

    def recorder(method, path, body, content_type):
        try:
            data = sm._call(method, path, body, content_type)
        except Exception as e:                       # noqa: BLE001 - recorded, then re-raised
            seen.append({"call": f"{method} {path}", "error": type(e).__name__,
                         "message": str(e)[:400]})
            raise
        kind = ("POST /job/digitise" if method == "POST" else
                "GET status" if path.endswith("/status") else "GET results")
        entry = {"call": f"{method} {path}", "kind": kind, "top": _keys(data),
                 "status": data.get("status") if isinstance(data, dict) else None}
        if isinstance(data, dict) and isinstance(data.get("usage"), dict):
            entry["usage"] = data["usage"]
            entry["usage_keys"] = _keys(data["usage"])
        if kind == "GET results" and isinstance(data, dict):
            docs = data.get("documents") or [{}]
            doc = docs[0] if isinstance(docs[0], dict) else {}
            pages = doc.get("pages") or [{}]
            page = pages[0] if isinstance(pages[0], dict) else {}
            entry["document_keys"] = _keys(doc)
            entry["page"] = _keys(page)
            entry["content_excerpt"] = str(page.get("content"))[:300]
            blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
            entry["blocks"] = len(blocks)
            entry["block_keys"] = _keys(blocks[0]) if blocks else []
            entry["layout_tags"] = sorted({str(b.get("layout_tag")) for b in blocks
                                           if isinstance(b, dict)})
        entry["vs_docs"] = compare(f"sarvam/{kind}", {
            "top": entry["top"], "usage": entry.get("usage_keys"),
            "document": entry.get("document_keys"), "page": entry.get("page")})
        seen.append(entry)
        return data

    rec: dict = {"sent": {"file": str(GAZETTE.relative_to(ROOT)), "page_range": [1, 1],
                          "language": "en-IN", "output_format": "html"}, "calls": seen}
    try:
        if job_id:
            # Re-read a job already paid for: GETs only, no new job.
            rec["sent"] = {"refetch_job_id": job_id, "note": "no new job submitted"}
            pages = sm.fetch_results(job_id, n_pages=1, output_format="html",
                                     _transport=recorder)
            res = None
        else:
            res = sm.digitise(GAZETTE, language="en-IN", output_format="html",
                              page_range=(1, 1), _transport=recorder)
            pages = list(res.pages)
        rec["result"] = {"pages": [(p.page, p.status) for p in pages],
                         "blocks": [len(p.blocks) for p in pages],
                         "model_written": [list(p.model_written) for p in pages],
                         "text_excerpt": (pages[0].text or "")[:600]}
        if res is not None:
            rec["result"].update({
                "basis": res.basis, "complete": res.complete,
                "jobs": [{"job_id": j.job_id, "run_id": j.run_id, "status": j.status}
                         for j in res.jobs],
                "est_cost_inr": res.est_cost_inr})
    except Exception as e:                           # noqa: BLE001 - recorded, not hidden
        rec["error"] = {"type": type(e).__name__, "message": str(e)[:500]}
    rec["call_count"] = len(seen)
    rec["statuses_seen"] = [s.get("status") for s in seen if s.get("kind") == "GET status"]
    return rec


def main(argv: list[str]) -> int:
    missing = [n for n, ok in (("VOYAGE_API_KEY", vm.available()),
                               ("SARVAM_API_KEY", sm.available())) if not ok]
    if missing:
        print(f"REFUSED: {', '.join(missing)} not set. No call was made.")
        return REFUSED
    if "--live" not in argv:
        print("Would make 3 Voyage calls (public statute excerpts) and 1 Sarvam Digitise "
              f"job on page 1 of {GAZETTE.name}. Re-run with --live.")
        return 0
    if "--sarvam-job" in argv:
        # Re-read one finished Sarvam job; no Voyage call, no new Sarvam job.
        record = {"run": date.today().isoformat(),
                  "sarvam": sarvam_smoke(argv[argv.index("--sarvam-job") + 1])}
        suffix = "_refetch"
    else:
        record = {"run": date.today().isoformat(), "voyage": voyage_smoke(),
                  "sarvam": sarvam_smoke()}
        suffix = ""
    out = ROOT / "reports" / f"smoke_adapters_{record['run']}{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"\nRecorded: {out.relative_to(ROOT)}")
    return 0 if all("error" not in v for k, v in record.items() if k != "run") else 1


def _test() -> None:
    import os
    import urllib.request
    from unittest import mock

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("smoke_adapters")
    network: list = []
    guard = mock.patch.object(urllib.request, "urlopen",
                              side_effect=lambda *a, **k: network.append(1) or 1 / 0)
    guard.start()
    held = {k: os.environ.pop(k, None) for k in ("VOYAGE_API_KEY", "SARVAM_API_KEY")}
    try:
        check(main(["--live"]) == REFUSED, "with no keys, --live refuses (exit 2)")
        os.environ["VOYAGE_API_KEY"] = "vk-test"
        check(main(["--live"]) == REFUSED, "with only one key, it still refuses")
        os.environ["SARVAM_API_KEY"] = "sk-test"
        check(main([]) == 0, "with both keys but no --live, it describes and calls nothing")
        check(not network, "...no network was touched")
        c = compare("voyage/rerank", {"top": ["object", "data", "model", "usage", "x"],
                                      "item": ["index"]})
        check(c["top"]["extra"] == ["x"] and c["item"]["missing"] == ["relevance_score"],
              "the docs-vs-live comparison reports extra and missing fields")
        ex = excerpts()
        check(len(ex) == 3 and all(e.startswith("Section 1") and len(e) <= EXCERPT_CHARS + 14
                                   for e in ex), "three short public statute excerpts")
        check(sm.privacy_check(GAZETTE).basis == sm.PUBLIC,
              "the Gazette PDF it would send passes the privacy guard as PUBLIC")
    finally:
        guard.stop()
        for k, v in held.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    check(not network, "no network was touched")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        raise SystemExit(main(sys.argv[1:]))
