"""Dense retrieval over the Companies Act, backed by a precomputed Voyage index.

`scripts/build_voyage_index.py --live` embeds every held section with `voyage-law-2`
(`checker/voyage_model.py`) and writes the vectors to `corpus/companies_act/
voyage_dense_index.json`. This module is the RUNTIME half: it loads that file (no
network) and, given a query, embeds ONLY the query live and ranks the precomputed
vectors against it by cosine similarity.

## Fail closed, in the dense_index.py / voyage_model.py sense

Two independent things can be missing -- the prebuilt index file, or a Voyage key to
embed the query with -- and either one makes dense retrieval unavailable. `search()`
raises `VoyageDenseUnavailable` rather than returning []: an empty list here would
read as "nothing is relevant", which is a different (and wrong) fact from "this
retriever did not run". `checker/retrieve.py` is the only caller that may treat the
raised exception as a reason to fall back to lexical alone, and it must say that it
did -- never silently serve a degraded result under the same label as a full one.

## Offline by construction, on the corpus side

The index is built once, out of band, and committed. A query is the only thing this
module ever sends to Voyage at request time -- one short string, not the corpus --
which keeps the per-query cost and latency bounded and auditable (`voyage_model.
cost_inr`). Nothing here re-embeds the corpus; that is the builder's job alone.

## The index must be the model it claims to be

`_load_index` refuses a file whose vectors are not `voyage_model.DOCUMENTED_DIM`
wide for the model it names. A re-dimensioned or hand-edited index is a different
index wearing this one's name, and ranking against it would silently answer a
question nobody asked -- the exact failure `voyage_model.parse_embeddings` already
refuses on the embeddings response itself.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from checker import voyage_model

INDEX_PATH = Path(__file__).resolve().parent.parent / "corpus" / "companies_act" / "voyage_dense_index.json"


class VoyageDenseUnavailable(RuntimeError):
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
    """(numbers, titles, vectors, model) from the index file at `path`.

    Cached per path, so the production file is parsed once per process and a test
    fixture at a different path gets its own cache entry rather than colliding with
    it -- no global to clear between tests.
    """
    if not path.is_file():
        raise VoyageDenseUnavailable(
            f"no prebuilt Voyage index at {path}. Run "
            f"'python3 scripts/build_voyage_index.py --live' with VOYAGE_API_KEY set.")
    try:
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VoyageDenseUnavailable(f"{path} could not be read as JSON: {e}") from None
    model = data.get("model")
    want_dim = voyage_model.DOCUMENTED_DIM.get(model)
    if want_dim is None:
        raise VoyageDenseUnavailable(
            f"{path} names model {model!r}, which is not one of this system's pinned "
            f"embedding models {tuple(voyage_model.DOCUMENTED_DIM)}. Refused rather than "
            f"ranked against: an unpinned model's numbers are not comparable to anything.")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise VoyageDenseUnavailable(f"{path} carries no sections; refused as empty")
    numbers: list[str] = []
    titles: dict[str, str] = {}
    vectors: list[tuple[float, ...]] = []
    seen: set[str] = set()
    for s in sections:
        number = str(s.get("number") or "").strip()
        vec = s.get("vector")
        if not number or number in seen:
            raise VoyageDenseUnavailable(f"{path}: a section entry has no number or repeats one")
        if (not isinstance(vec, list) or len(vec) != want_dim
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vec)):
            raise VoyageDenseUnavailable(
                f"{path}: section {number} does not carry a {want_dim}-dimensional vector "
                f"for {model} -- the index does not match the model it names")
        seen.add(number)
        numbers.append(number)
        titles[number] = str(s.get("title") or "")
        vectors.append(tuple(float(v) for v in vec))
    return tuple(numbers), titles, tuple(vectors), model


def available(path: Path = INDEX_PATH) -> tuple[bool, str]:
    """Probe without raising, so a caller can report 'not runnable' honestly.

    Two independent gates: the index file must exist and parse, AND a key must be
    configured to embed the query with. Either alone is not enough to serve a result.
    """
    try:
        numbers, _titles, _vecs, model = _load_index(path)
    except VoyageDenseUnavailable as e:
        return False, str(e)
    if not voyage_model.available():
        return False, "VOYAGE_API_KEY is not set; the index exists but the query cannot be embedded"
    return True, f"{len(numbers)} sections indexed with {model}"


def search(query: str, top_k: int = 5, *, path: Path = INDEX_PATH,
           _embed=None) -> list[tuple[str, str, float]]:
    """(section_number, title, cosine) best-first. Raises VoyageDenseUnavailable rather
    than falling back -- see the module docstring.

    `_embed` is an injection point: a callable `query -> vector`. The gate passes a
    fixture-backed stub so this module's own test opens no socket; production leaves
    it unset and the real query goes to Voyage through `voyage_model.embed`.
    """
    numbers, titles, vectors, model = _load_index(path)
    if _embed is not None:
        qvec = list(_embed(query))
    else:
        if not voyage_model.available():
            raise VoyageDenseUnavailable(
                "VOYAGE_API_KEY is not set; the index exists but the query cannot be embedded")
        vecs, _call = voyage_model.embed([query], input_type="query", model=model)
        qvec = vecs[0]
    scored = [(n, titles[n], _cosine(qvec, v)) for n, v in zip(numbers, vectors)]
    scored.sort(key=lambda t: -t[2])
    return scored[:top_k]


def best_section(query: str, *, path: Path = INDEX_PATH, _embed=None) -> str | None:
    hits = search(query, top_k=1, path=path, _embed=_embed)
    return hits[0][0] if hits else None


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

    print("voyage_dense")

    check(_cosine([1.0, 0.0], [1.0, 0.0]) == 1.0, "identical unit vectors cosine to 1.0")
    check(abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-12, "orthogonal vectors cosine to 0.0")
    check(_cosine([0.0, 0.0], [1.0, 0.0]) == 0.0, "a zero vector cosines to 0.0, never divides by zero")

    DIM = voyage_model.DOCUMENTED_DIM[voyage_model.LAW]

    def vec(*head: float) -> list[float]:
        return [*head] + [0.0] * (DIM - len(head))

    missing_path = Path("/nonexistent/voyage_dense_index_does_not_exist.json")
    try:
        _load_index(missing_path)
        check(False, "a missing index file raises VoyageDenseUnavailable")
    except VoyageDenseUnavailable as e:
        check("no prebuilt Voyage index" in str(e), f"a missing index file is refused ({e})")
    ok_avail, why = available(missing_path)
    check(not ok_avail and "no prebuilt Voyage index" in why,
          "available() reports the same reason without raising")

    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "index.json"
        good.write_text(json.dumps({
            "model": voyage_model.LAW,
            "sections": [
                {"number": "185", "title": "Loan to directors, etc.", "vector": vec(1.0, 0.0)},
                {"number": "188", "title": "Related party transactions", "vector": vec(0.0, 1.0)},
                {"number": "173", "title": "Meetings of Board", "vector": vec(0.7, 0.7)},
            ],
        }))

        held_key = os.environ.pop("VOYAGE_API_KEY", None)
        try:
            ok_avail, why = available(good)
            check(not ok_avail and "VOYAGE_API_KEY" in why,
                  f"a real index with no key is unavailable, and says why ({why})")

            e = None
            try:
                search("loans to directors", path=good)
            except VoyageDenseUnavailable as exc:
                e = exc
            check(isinstance(e, VoyageDenseUnavailable),
                  "search() with no key and no injected embedder raises, never returns []")

            hits = search("loans to directors", top_k=3, path=good,
                          _embed=lambda q: vec(1.0, 0.0))
            check([h[0] for h in hits][0] == "185",
                  f"an injected query vector matching s.185's exactly ranks it first ({hits})")
            check(len(hits) == 3 and hits == sorted(hits, key=lambda h: -h[2]),
                  "hits are best-first and top_k is respected")
            check(all(isinstance(h[2], float) for h in hits), "every hit carries a cosine score")
            check(hits[0][1] == "Loan to directors, etc.",
                  "the title comes from the index record, verbatim")

            os.environ["VOYAGE_API_KEY"] = "vk-TEST-voyage-dense"
            ok_avail, why = available(good)
            check(ok_avail, f"with a key AND a valid index, available() is True ({why})")

            hits2 = search("related party transactions", top_k=1, path=good,
                           _embed=lambda q: vec(0.0, 1.0))
            check(hits2[0][0] == "188", "a different injected vector ranks a different section first")

            with mock.patch.object(voyage_model, "_post", side_effect=AssertionError("no network")):
                search("loans to directors", path=good, _embed=lambda q: vec(1.0, 0.0))
            check(True, "an injected _embed bypasses voyage_model entirely -- no transport call")
        finally:
            os.environ.pop("VOYAGE_API_KEY", None)
            if held_key is not None:
                os.environ["VOYAGE_API_KEY"] = held_key

        # --- the model/dimension guard --------------------------------------------
        wrong_model = Path(td) / "wrong_model.json"
        wrong_model.write_text(json.dumps({
            "model": "voyage-3", "sections": [{"number": "1", "title": "x", "vector": vec(1.0)}]}))
        e = None
        try:
            _load_index(wrong_model)
        except VoyageDenseUnavailable as exc:
            e = exc
        check(isinstance(e, VoyageDenseUnavailable) and "voyage-3" in str(e),
              "an index naming an unpinned model is refused, not ranked against")

        wrong_dim = Path(td) / "wrong_dim.json"
        wrong_dim.write_text(json.dumps({
            "model": voyage_model.LAW,
            "sections": [{"number": "1", "title": "x", "vector": [0.1, 0.2, 0.3]}]}))
        e = None
        try:
            _load_index(wrong_dim)
        except VoyageDenseUnavailable as exc:
            e = exc
        check(isinstance(e, VoyageDenseUnavailable) and "dimensional" in str(e),
              "an index whose vectors are the wrong width is refused, never silently ranked")

        dup = Path(td) / "dup.json"
        dup.write_text(json.dumps({
            "model": voyage_model.LAW,
            "sections": [{"number": "1", "title": "x", "vector": vec(1.0)},
                        {"number": "1", "title": "y", "vector": vec(0.5)}]}))
        e = None
        try:
            _load_index(dup)
        except VoyageDenseUnavailable as exc:
            e = exc
        check(isinstance(e, VoyageDenseUnavailable), "a repeated section number in the index is refused")

        empty = Path(td) / "empty.json"
        empty.write_text(json.dumps({"model": voyage_model.LAW, "sections": []}))
        e = None
        try:
            _load_index(empty)
        except VoyageDenseUnavailable as exc:
            e = exc
        check(isinstance(e, VoyageDenseUnavailable), "an index with zero sections is refused as empty")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
