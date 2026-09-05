"""BM25 ranking over structural chunks — zero dependencies, before any embedding.

The retrieval eval (checker/retrieval_eval.py) measured the naive term-overlap
selector at precision@1 = 0.20. The obvious next move is a neural embedding layer,
but that needs a heavy dependency (torch / sentence-transformers) or a paid API,
against a project rule — "No new dependency without a stated reason" — and a
zero-third-party-deps architecture. So the disciplined first step is not the
embedding; it is to find out whether a classical, dependency-free ranker already
clears the bar. If BM25 solves it, the embedding dependency is unnecessary (YAGNI).
If BM25 also stalls, THAT is the measured, rigorous case for the dependency —
lexical methods have a semantic ceiling, shown with a number, not asserted.

## What this is

Okapi BM25, the standard bag-of-words ranker, implemented over plain term counts.
No model, no network, no third-party package — just IDF weighting and length
normalisation, which is arithmetic. It ranks a fixed set of chunks for a query.

BM25 parameters k1 and b are the textbook defaults (1.5, 0.75); they are named
constants, not magic numbers, and can be tuned against the eval if a reason
arises. Tokenisation is lowercase word tokens minus a small stopword set — the
same instinct as ground_span._terms, kept separate so the ranker is self-contained.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

# Textbook BM25 defaults. k1 controls term-frequency saturation; b controls how
# strongly document length is normalised.
K1 = 1.5
B = 0.75

_STOP = frozenset("""
the a an and or of to in on for by as at is are be been being this that these those
which who whom whose with without within under over into from such shall may must
not no any all each every other than then thus so if it its section clause sub company
companies means include includes referred person case time made specify specified
""".split())


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower())
            if len(w) >= 3 and w not in _STOP]


@dataclass(frozen=True)
class Doc:
    id: str
    tokens: tuple[str, ...]


class BM25:
    """A BM25 index over a fixed corpus of (id, text) documents."""

    def __init__(self, docs: list[tuple[str, str]], *, k1: float = K1, b: float = B):
        self.k1, self.b = k1, b
        self.docs: list[Doc] = [Doc(i, tuple(tokenize(t))) for i, t in docs]
        self.N = len(self.docs)
        self._tf: list[Counter] = [Counter(d.tokens) for d in self.docs]
        self._len = [len(d.tokens) for d in self.docs]
        self.avgdl = (sum(self._len) / self.N) if self.N else 0.0
        # document frequency per term
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d.tokens))
        self._df = df

    def _idf(self, term: str) -> float:
        n = self._df.get(term, 0)
        # BM25 idf with the +1 inside the log so it is never negative.
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query: str, doc_index: int) -> float:
        q = tokenize(query)
        if not q or self.avgdl == 0:
            return 0.0
        tf = self._tf[doc_index]
        dl = self._len[doc_index]
        s = 0.0
        for term in q:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = self._idf(term)
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s += idf * (f * (self.k1 + 1)) / denom
        return s

    def rank(self, query: str) -> list[tuple[str, float]]:
        """(id, score) for every doc, best first. Ties keep corpus order (stable)."""
        scored = [(self.docs[i].id, self.score(query, i)) for i in range(self.N)]
        return sorted(scored, key=lambda t: -t[1])

    def top(self, query: str) -> str | None:
        """The single best-scoring doc id, or None if nothing scores above zero."""
        ranked = self.rank(query)
        if not ranked or ranked[0][1] <= 0.0:
            return None
        return ranked[0][0]


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

    print("lexical_rank")

    # ── tokenisation drops stopwords and short tokens ───────────────────────
    toks = tokenize("The paid-up share capital of a small company")
    check("paid" in toks and "capital" in toks and "small" in toks,
          "content words survive tokenisation")
    check("the" not in toks and "of" not in toks and "a" not in toks,
          "stopwords are dropped")

    # ── a tiny corpus ranks the on-topic doc first ──────────────────────────
    corpus = [
        ("capital", "paid up share capital of a company does not exceed a limit"),
        ("turnover", "turnover of a company for the preceding financial year"),
        ("agm", "annual general meeting held each year within a period of months"),
    ]
    bm = BM25(corpus)
    check(bm.top("share capital limit") == "capital",
          f"a capital query ranks the capital doc first ({bm.top('share capital limit')})")
    check(bm.top("turnover financial year") == "turnover",
          "a turnover query ranks the turnover doc first")
    check(bm.top("annual general meeting") == "agm",
          "an AGM query ranks the AGM doc first")

    # ── a query with no shared content term scores nothing ──────────────────
    check(bm.top("photosynthesis chlorophyll") is None,
          "a query sharing no term returns None, not a false top hit")

    # ── IDF: a rare term outweighs a common one ─────────────────────────────
    # "company" appears in all three docs (common -> low idf); "turnover" in one
    # (rare -> high idf). A doc matching the rare term should win.
    check(bm.top("company turnover") == "turnover",
          "the rare discriminating term drives the ranking, not the common one")

    # ── length normalisation: a short exact doc beats a long diluted one ────
    corpus2 = [
        ("short", "quorum two directors"),
        ("long", "quorum " + "padding word here and there " * 40 + " two directors"),
    ]
    bm2 = BM25(corpus2)
    check(bm2.top("quorum two directors") == "short",
          "length normalisation prefers the concise on-topic doc")

    # ── deterministic: same query, same ranking ─────────────────────────────
    check(bm.rank("share capital") == bm.rank("share capital"),
          "ranking is deterministic")

    # ── empty corpus / empty query degrade quietly ──────────────────────────
    check(BM25([]).top("anything") is None, "an empty corpus tops nothing")
    check(bm.top("") is None, "an empty query tops nothing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
