"""Dense retrieval over judgment BODIES, backed by a precomputed Voyage index.

Mirrors `checker/voyage_dense.py` (#99's Companies Act dense activation) exactly, for
judgments. `scripts/build_judgment_voyage_index.py --live` fetches judgment PDFs via
`checker.sources.judgments_open` (keyless S3), extracts their text, and embeds a bounded
slice of each with `voyage-law-2` (`checker/voyage_model.py`), writing the vectors to
`corpus/judgments/voyage_dense_index.json`. This module is the RUNTIME half: it loads that
file (no network) and, given a query, embeds ONLY the query live and ranks the precomputed
vectors against it by cosine similarity.

## Why this closes the gap `checker/sources/judgment_index.py` names

`judgment_index.search_index` matches a query's words against PARTY/TITLE/COURT metadata
only -- there is no topic field in the dataset. "oppression and mismanagement cases" or
"cases on related-party transactions" name no party, so metadata search returns an honest
[], even though judgments on exactly that topic sit in the index. This module searches the
judgments' own WORDS (via their embedded bodies), which is where the topic signal lives.

## Fail closed, in the voyage_dense.py sense

Two independent things can be missing -- the prebuilt index file, or a Voyage key to embed
the query with -- and either one makes dense retrieval unavailable. `search()` raises
`JudgmentDenseUnavailable` rather than returning []: an empty list here would read as
"no judgment is on topic", which is a different (and wrong) fact from "this retriever did
not run". The caller (`judgment_index.discover`) is the only place that may treat the raised
exception as a reason to fall back to metadata alone, and it falls back to EXACTLY today's
behaviour -- never worse.

## The index must be the model it claims to be

`_load_index` refuses a file whose vectors are not `voyage_model.DOCUMENTED_DIM` wide for the
model it names, and a repeated or missing `s3_key` is refused rather than silently merged or
dropped -- the same guards `voyage_dense._load_index` applies to section numbers.

## Identity is the s3_key, not a title

A judgment has no stable "number" the way a Companies Act section does. `s3_key` is the one
field every `JudgmentRef` already carries that both identifies a row and is fetchable
(`checker/sources/judgment_index.JudgmentRef`), so it is this index's identity -- the same
role `number` plays in `voyage_dense.py`. This module never invents a judgment: a search hit
is only ever an s3_key this index itself holds a vector for, and the caller fusing it against
the real committed judgment index drops any hit that is not also a real row there (mirroring
`checker/retrieve.py`'s `_row_for_number` guard against fabricating a provision).

Run:  PYTHONPATH=. python3 checker/judgment_dense.py --test
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from checker import voyage_model

INDEX_PATH = Path(__file__).resolve().parent.parent / "corpus" / "judgments" / "voyage_dense_index.json"


class JudgmentDenseUnavailable(RuntimeError):
    """Raised instead of returning []. Either the prebuilt index is missing, or there
    is no key to embed the query with -- never degraded to a silent empty result."""


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da * db)


@lru_cache(maxsize=8)
def _load_index(path: Path) -> tuple[tuple[str, ...], dict[str, str], tuple[tuple[float, ...], ...], str]:
    """(s3_keys, titles, vectors, model) from the index file at `path`.

    Cached per path, so the production file is parsed once per process and a test fixture
    at a different path gets its own cache entry rather than colliding with it -- no global
    to clear between tests.
    """
    if not path.is_file():
        raise JudgmentDenseUnavailable(
            f"no prebuilt Voyage judgment index at {path}. Run "
            f"'python3 scripts/build_judgment_voyage_index.py --live' with VOYAGE_API_KEY set.")
    try:
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise JudgmentDenseUnavailable(f"{path} could not be read as JSON: {e}") from None
    model = data.get("model")
    want_dim = voyage_model.DOCUMENTED_DIM.get(model)
    if want_dim is None:
        raise JudgmentDenseUnavailable(
            f"{path} names model {model!r}, which is not one of this system's pinned "
            f"embedding models {tuple(voyage_model.DOCUMENTED_DIM)}. Refused rather than "
            f"ranked against: an unpinned model's numbers are not comparable to anything.")
    judgments = data.get("judgments")
    if not isinstance(judgments, list) or not judgments:
        raise JudgmentDenseUnavailable(f"{path} carries no judgments; refused as empty")
    keys: list[str] = []
    titles: dict[str, str] = {}
    vectors: list[tuple[float, ...]] = []
    seen: set[str] = set()
    for j in judgments:
        s3_key = str(j.get("s3_key") or "").strip()
        vec = j.get("vector")
        if not s3_key or s3_key in seen:
            raise JudgmentDenseUnavailable(f"{path}: a judgment entry has no s3_key or repeats one")
        if (not isinstance(vec, list) or len(vec) != want_dim
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vec)):
            raise JudgmentDenseUnavailable(
                f"{path}: judgment {s3_key} does not carry a {want_dim}-dimensional vector "
                f"for {model} -- the index does not match the model it names")
        seen.add(s3_key)
        keys.append(s3_key)
        titles[s3_key] = str(j.get("title") or "")
        vectors.append(tuple(float(v) for v in vec))
    return tuple(keys), titles, tuple(vectors), model


def available(path: Path = INDEX_PATH) -> tuple[bool, str]:
    """Probe without raising, so a caller can report 'not runnable' honestly.

    Two independent gates: the index file must exist and parse, AND a key must be
    configured to embed the query with. Either alone is not enough to serve a result.
    """
    try:
        keys, _titles, _vecs, model = _load_index(path)
    except JudgmentDenseUnavailable as e:
        return False, str(e)
    if not voyage_model.available():
        return False, "VOYAGE_API_KEY is not set; the index exists but the query cannot be embedded"
    return True, f"{len(keys)} judgments indexed with {model}"


def search(query: str, top_k: int = 5, *, path: Path = INDEX_PATH,
           _embed=None) -> list[tuple[str, str, float]]:
    """(s3_key, title, cosine) best-first. Raises JudgmentDenseUnavailable rather than
    falling back -- see the module docstring.

    `_embed` is an injection point: a callable `query -> vector`. The gate passes a
    fixture-backed stub so this module's own test opens no socket; production leaves it
    unset and the real query goes to Voyage through `voyage_model.embed`.
    """
    keys, titles, vectors, model = _load_index(path)
    if _embed is not None:
        qvec = list(_embed(query))
    else:
        if not voyage_model.available():
            raise JudgmentDenseUnavailable(
                "VOYAGE_API_KEY is not set; the index exists but the query cannot be embedded")
        vecs, _call = voyage_model.embed([query], input_type="query", model=model)
        qvec = vecs[0]
    scored = [(k, titles[k], _cosine(qvec, v)) for k, v in zip(keys, vectors)]
    scored.sort(key=lambda t: -t[2])
    return scored[:top_k]


def _test() -> None:
    import os
    import tempfile
    from unittest import mock

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("judgment_dense")

    check(_cosine([1.0, 0.0], [1.0, 0.0]) == 1.0, "identical unit vectors cosine to 1.0")
    check(abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-12, "orthogonal vectors cosine to 0.0")
    check(_cosine([0.0, 0.0], [1.0, 0.0]) == 0.0, "a zero vector cosines to 0.0, never divides by zero")

    DIM = voyage_model.DOCUMENTED_DIM[voyage_model.LAW]

    def vec(*head: float) -> list[float]:
        return [*head] + [0.0] * (DIM - len(head))

    missing_path = Path("/nonexistent/judgment_voyage_index_does_not_exist.json")
    try:
        _load_index(missing_path)
        check(False, "a missing index file raises JudgmentDenseUnavailable")
    except JudgmentDenseUnavailable as e:
        check("no prebuilt Voyage judgment index" in str(e), f"a missing index file is refused ({e})")
    ok_avail, why = available(missing_path)
    check(not ok_avail and "no prebuilt Voyage judgment index" in why,
          "available() reports the same reason without raising")

    TATA_KEY = "data/pdf/year=2021/english/tata-mistry_EN.pdf"
    OPPRESSION_KEY = "data/pdf/year=2019/english/oppression_EN.pdf"
    DATAPRIV_KEY = "data/pdf/year=2026/english/data-priv_EN.pdf"

    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "index.json"
        good.write_text(json.dumps({
            "model": voyage_model.LAW,
            "judgments": [
                {"s3_key": TATA_KEY, "title": "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                 "vector": vec(1.0, 0.0)},
                {"s3_key": OPPRESSION_KEY,
                 "title": "Some Company v. Registrar (oppression and mismanagement)",
                 "vector": vec(0.0, 1.0)},
                {"s3_key": DATAPRIV_KEY, "title": "ABC Ltd v. Union of India (data protection)",
                 "vector": vec(0.7, 0.7)},
            ],
        }))

        held_key = os.environ.pop("VOYAGE_API_KEY", None)
        try:
            ok_avail, why = available(good)
            check(not ok_avail and "VOYAGE_API_KEY" in why,
                  f"a real index with no key is unavailable, and says why ({why})")

            e = None
            try:
                search("removal of directors", path=good)
            except JudgmentDenseUnavailable as exc:
                e = exc
            check(isinstance(e, JudgmentDenseUnavailable),
                  "search() with no key and no injected embedder raises, never returns []")

            hits = search("removal of directors", top_k=3, path=good,
                          _embed=lambda q: vec(1.0, 0.0))
            check([h[0] for h in hits][0] == TATA_KEY,
                  f"an injected query vector matching the Tata/Cyrus row exactly ranks it first ({hits})")
            check(len(hits) == 3 and hits == sorted(hits, key=lambda h: -h[2]),
                  "hits are best-first and top_k is respected")
            check(all(isinstance(h[2], float) for h in hits), "every hit carries a cosine score")
            check(hits[0][1] == "Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd",
                  "the title comes from the index record, verbatim")

            os.environ["VOYAGE_API_KEY"] = "vk-TEST-judgment-dense"
            ok_avail, why = available(good)
            check(ok_avail, f"with a key AND a valid index, available() is True ({why})")

            hits2 = search("oppression and mismanagement", top_k=1, path=good,
                           _embed=lambda q: vec(0.0, 1.0))
            check(hits2[0][0] == OPPRESSION_KEY,
                  "a different injected vector ranks a different judgment first")

            with mock.patch.object(voyage_model, "_post", side_effect=AssertionError("no network")):
                search("removal of directors", path=good, _embed=lambda q: vec(1.0, 0.0))
            check(True, "an injected _embed bypasses voyage_model entirely -- no transport call")
        finally:
            os.environ.pop("VOYAGE_API_KEY", None)
            if held_key is not None:
                os.environ["VOYAGE_API_KEY"] = held_key

        # --- the model/dimension guard --------------------------------------------
        wrong_model = Path(td) / "wrong_model.json"
        wrong_model.write_text(json.dumps({
            "model": "voyage-3",
            "judgments": [{"s3_key": TATA_KEY, "title": "x", "vector": vec(1.0)}]}))
        e = None
        try:
            _load_index(wrong_model)
        except JudgmentDenseUnavailable as exc:
            e = exc
        check(isinstance(e, JudgmentDenseUnavailable) and "voyage-3" in str(e),
              "an index naming an unpinned model is refused, not ranked against")

        wrong_dim = Path(td) / "wrong_dim.json"
        wrong_dim.write_text(json.dumps({
            "model": voyage_model.LAW,
            "judgments": [{"s3_key": TATA_KEY, "title": "x", "vector": [0.1, 0.2, 0.3]}]}))
        e = None
        try:
            _load_index(wrong_dim)
        except JudgmentDenseUnavailable as exc:
            e = exc
        check(isinstance(e, JudgmentDenseUnavailable) and "dimensional" in str(e),
              "an index whose vectors are the wrong width is refused, never silently ranked")

        dup = Path(td) / "dup.json"
        dup.write_text(json.dumps({
            "model": voyage_model.LAW,
            "judgments": [{"s3_key": TATA_KEY, "title": "x", "vector": vec(1.0)},
                          {"s3_key": TATA_KEY, "title": "y", "vector": vec(0.5)}]}))
        e = None
        try:
            _load_index(dup)
        except JudgmentDenseUnavailable as exc:
            e = exc
        check(isinstance(e, JudgmentDenseUnavailable), "a repeated s3_key in the index is refused")

        empty = Path(td) / "empty.json"
        empty.write_text(json.dumps({"model": voyage_model.LAW, "judgments": []}))
        e = None
        try:
            _load_index(empty)
        except JudgmentDenseUnavailable as exc:
            e = exc
        check(isinstance(e, JudgmentDenseUnavailable), "an index with zero judgments is refused as empty")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
