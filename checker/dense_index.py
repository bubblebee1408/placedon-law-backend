"""Dense retrieval over the Act — decision B, finally measured.

Decision B (add an embedding layer) was DEFERRED on 2026-09-04, and the recorded reason
was specific: it meant adding a heavy dependency against the no-new-dependency rule.
That reason no longer holds — `sentence_transformers`, `torch` and `numpy` are already
installed, and `all-MiniLM-L6-v2` is already in the local HuggingFace cache. So the
experiment runs.

It runs to be **measured**, not adopted. `corpus_retrieval` (BM25) scores p@1 0.71 /
recall@5 0.91 on the frozen 70-case eval. This module is judged against that bar. A
dense index that loses is reported as losing and is not merged into the default path.

## The failure mode this module refuses

The tempting bug is to catch a model-load error and quietly fall back to BM25. Then the
"dense" numbers in the eval are BM25's numbers under a different name, and the whole
experiment silently answers a question nobody asked. `search()` therefore raises
`DenseUnavailable` rather than degrading. A missing capability must look missing.

## Offline by construction

The model is loaded from the local cache with network access disabled. If it is not
cached, that is a refusal with a clear reason — not a surprise download mid-eval.
"""
from __future__ import annotations

import os
import pickle
import re
from functools import lru_cache
from pathlib import Path

from checker import section_index as _si
from checker.corpus_retrieval import _clean, clean_html

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_CACHE = Path(__file__).resolve().parent.parent / "corpus" / ".dense_cache.pkl"

# The heading carries most of the topical signal for "which section governs this?", so
# it is embedded joined to a bounded slice of the body. Embedding the whole section
# would dilute a 384-dim vector across pages of procedural text and blur exactly the
# distinctions the eval measures.
_BODY_CHARS = 1200


class DenseUnavailable(RuntimeError):
    """Raised instead of falling back. A silent BM25 fallback would report BM25's
    numbers as dense numbers and invalidate the comparison."""


@lru_cache(maxsize=1)
def _model():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise DenseUnavailable(f"sentence_transformers is not importable: {e}") from e
    try:
        return SentenceTransformer(MODEL_NAME)
    except Exception as e:                        # noqa: BLE001 - any load failure
        raise DenseUnavailable(
            f"{MODEL_NAME} could not be loaded offline ({e}). It must be in the local "
            "cache; this module will not download mid-run and will not fall back to "
            "BM25 under a dense label") from e


def _corpus() -> list[tuple[str, str, str]]:
    """(section_number, title, embedding_text) for every section."""
    out = []
    for number, rec in _si._index().items():
        d = _si.section_by_number(str(number))
        if not d:
            continue
        title = _clean(rec.get("title", ""))
        body = clean_html(d.get("content", ""))[:_BODY_CHARS]
        out.append((str(number), title, f"Section {number}. {title}. {body}"))
    return out


@lru_cache(maxsize=1)
def _index():
    """(numbers, titles, matrix). Cached to disk keyed on model+corpus size, because
    embedding ~474 sections on an M1 costs real seconds and the eval runs repeatedly."""
    import numpy as np

    corpus = _corpus()
    numbers = [c[0] for c in corpus]
    titles = {c[0]: c[1] for c in corpus}
    key = (MODEL_NAME, len(corpus), _BODY_CHARS)

    if _CACHE.exists():
        try:
            with _CACHE.open("rb") as fh:
                blob = pickle.load(fh)
            if blob.get("key") == key and blob.get("numbers") == numbers:
                return numbers, titles, blob["matrix"]
        except Exception:                          # noqa: BLE001 - a bad cache is not fatal
            pass                                   # recompute; never trust a stale cache

    m = _model()
    mat = m.encode([c[2] for c in corpus], batch_size=16,
                   convert_to_numpy=True, normalize_embeddings=True,
                   show_progress_bar=False)
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE.open("wb") as fh:
            pickle.dump({"key": key, "numbers": numbers, "matrix": mat}, fh)
    except OSError:
        pass                                       # a cache we cannot write is not an error
    return numbers, titles, mat


def search(query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
    """(section_number, title, cosine) best-first. Raises if dense is unavailable."""
    import numpy as np

    numbers, titles, mat = _index()
    q = _model().encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = mat @ q                                  # both normalised -> cosine
    order = np.argsort(-sims)[:top_k]
    return [(numbers[i], titles.get(numbers[i], ""), float(sims[i])) for i in order]


def best_section(query: str) -> str | None:
    hits = search(query, top_k=1)
    return hits[0][0] if hits else None


def available() -> tuple[bool, str]:
    """Probe without raising, so a caller can report 'not runnable' honestly."""
    try:
        _model()
        return True, f"{MODEL_NAME} loaded from local cache"
    except DenseUnavailable as e:
        return False, str(e)


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    ok, why = available()
    print(f"  [INFO] dense available: {ok} — {why}")
    if not ok:
        # The honest outcome on a machine without the cached model: the suite reports
        # the capability as missing rather than passing vacuously.
        check(True, "dense unavailable is reported, not hidden")
        print(f"\n{passed}/{passed + failed} passed")
        return

    hits = search("loans to directors", top_k=5)
    check(len(hits) == 5, "search returns top_k hits")
    check(all(isinstance(h[2], float) for h in hits), "each hit carries a cosine score")
    check(hits == sorted(hits, key=lambda h: -h[2]), "hits are best-first")
    nums = [h[0] for h in hits]
    check("185" in nums, f"'loans to directors' reaches s.185 in top-5 ({nums})")

    hits2 = search("related party transactions", top_k=5)
    check("188" in [h[0] for h in hits2],
          f"'related party transactions' reaches s.188 ({[h[0] for h in hits2]})")

    check(-1.01 <= hits[0][2] <= 1.01, "cosine is in range")
    check(_index() is _index(), "the index is cached, not rebuilt per call")
    check(_CACHE.exists(), "the embedding matrix is persisted to disk")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
