"""Cross-section retrieval: given a question, find the SECTION that governs it.

`chunk_retrieval` ranks chunks WITHIN a known section (precision@1 0.62). This is
the harder, truer accuracy question the strategy critique implies: given "can a
company lend to its director?", does retrieval even reach s.185? Until now that was
untested. This module answers it — BM25 over every section of the Act, with the
section HEADING boosted because a title like "Loans to directors, etc." is the
strongest single signal of what a section governs.

Zero dependencies (BM25 is arithmetic). The corpus index is built once and cached.
Heading boost is implemented by repeating the heading text so its terms carry more
term-frequency weight — crude but effective, and tunable against the eval.
"""
from __future__ import annotations

import html as _html
import re
from functools import lru_cache

from checker import section_index as _si
from checker.lexical_rank import BM25
from checker.structural_chunk import clean_html

# How many times the heading is repeated into the section document. A heading is
# a dense statement of the section's subject, so weighting it up sharply improves
# "which section governs this" without touching the body text.
_HEADING_BOOST = 5

# Producer Company provisions (Part IXA, s.378A-378ZU) are a parallel regime
# that shadows the general sections -- a query about "board powers" should reach
# s.179, not the producer-company variant s.378R. Unless the query is explicitly
# about producer companies, their score is demoted (not removed -- a producer
# query still finds them). This is a structural prior, not eval tuning: the two
# regimes genuinely coexist and a general question belongs to the general one.
_PRODUCER_PENALTY = 0.2
_PRODUCER_SECTION = re.compile(r"^378[A-Z]?", re.I)


def _clean(raw: str) -> str:
    s = re.sub(r"<[^>]+>", " ", raw or "")
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _index() -> tuple[BM25, dict]:
    """(BM25 over all sections, {section_number: title}). Built once."""
    idx = _si._index()
    docs: list[tuple[str, str]] = []
    titles: dict[str, str] = {}
    for number, rec in idx.items():
        d = _si.section_by_number(str(number))
        if not d:
            continue
        title = _clean(rec.get("title", ""))
        body = clean_html(d.get("content", ""))
        titles[str(number)] = title
        # Heading boosted by repetition; body appended once.
        doc = ((title + " ") * _HEADING_BOOST) + body
        docs.append((str(number), doc))
    return BM25(docs), titles


def search(query: str, top_k: int = 5) -> list[tuple[str, str, float]]:
    """(section_number, title, score) best-first, up to top_k, score>0 only.

    Producer Company sections are demoted unless the query is about them, so the
    general regime wins a general question.
    """
    bm, titles = _index()
    about_producer = "producer" in query.lower()
    scored: list[tuple[str, str, float]] = []
    for num, score in bm.rank(query):
        if score <= 0.0:
            continue
        if not about_producer and _PRODUCER_SECTION.match(num):
            score *= _PRODUCER_PENALTY
        scored.append((num, titles.get(num, ""), score))
    scored.sort(key=lambda t: -t[2])
    return scored[:top_k]


def best_section(query: str) -> str | None:
    """The section number most likely to govern the query, or None."""
    hits = search(query, top_k=1)
    return hits[0][0] if hits else None


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

    print("corpus_retrieval")

    # The index builds and covers the corpus.
    bm, titles = _index()
    check(bm.N > 400, f"the corpus index covers the sections ({bm.N})")

    # A handful of unambiguous cross-section cases (the question names the concept
    # the section governs; the expected section is structural, not interpretive).
    seed = [
        ("can a company give a loan to its director", "185"),
        ("related party transaction approval", "188"),
        ("inter-corporate loan and investment limit", "186"),
        ("annual general meeting", "96"),
        ("meetings of the board of directors", "173"),
        ("corporate social responsibility", "135"),
        ("definitions", "2"),
    ]
    correct = 0
    for q, expected in seed:
        got = best_section(q)
        top5 = [n for n, _, _ in search(q, 5)]
        hit = got == expected
        correct += hit
        in5 = expected in top5
        print(f"    {'OK ' if hit else ('~5 ' if in5 else 'MISS')} q={q[:40]:42} "
              f"exp={expected:4} got={got} top5={top5}")

    p_at_1 = correct / len(seed)
    check(p_at_1 >= 0.5,
          f"cross-section precision@1 clears an initial floor ({correct}/{len(seed)} "
          f"= {p_at_1:.2f})")
    # recall@5 is the more forgiving, and more useful, first metric.
    recall5 = sum(expected in [n for n, _, _ in search(q, 5)] for q, expected in seed)
    check(recall5 >= len(seed) - 1,
          f"cross-section recall@5 is high ({recall5}/{len(seed)})")

    check(best_section("xylophone photosynthesis quark") is None
          or best_section("xylophone photosynthesis quark") not in (n for n, _ in seed),
          "an off-topic query does not confidently return a governance section")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
