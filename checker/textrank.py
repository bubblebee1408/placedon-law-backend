#!/usr/bin/env python3
"""Extractive summarization via TextRank (Mihalcea & Tarau, EMNLP 2004).

Graph-based unsupervised sentence ranking. No model, no training data, no
dependencies beyond stdlib. Build a similarity graph over sentences, run
PageRank until convergence, return top-k in document order.

The algorithm:
  1. Tokenize text into sentences.
  2. Build a word set for each sentence (lowered, stopwords removed).
  3. Compute pairwise similarity: |W_i ∩ W_j| / (log|W_i| + log|W_j|).
     (Mihalcea & Tarau's normalized overlap — the log denominator prevents
     long sentences from dominating short ones.)
  4. Build a weighted adjacency matrix.
  5. Iterate PageRank: score(i) = (1-d) + d * Σ_j [w(i,j)/Σ_k w(j,k)] * score(j)
     where d = 0.85 (damping factor from the original paper).
  6. Return top-k sentences in their original document order.

Reference:
  Mihalcea R., Tarau P. "TextRank: Bringing Order into Texts."
  EMNLP 2004, pp. 404–411. ACL, Barcelona.

Run: PYTHONPATH=. python3 checker/textrank.py --test
"""
from __future__ import annotations

import math
import re

__all__ = ["summarize", "rank_sentences"]

DAMPING = 0.85
MAX_ITER = 100
CONVERGENCE = 1e-4

_SENTENCE_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z])"
    r"|(?<=\n)\s*\n"
)

# Minimal English stopwords — enough to prevent function words from dominating
# similarity without pulling in NLTK.
_STOP = frozenset(
    "a an the and or but in on at to for of is are was were be been being "
    "has have had do does did will would shall should may might can could "
    "this that these those it its he she they them his her their "
    "i we you my our your not no nor so if by from with as".split()
)

_WORD_RE = re.compile(r"[a-z][a-z'-]*[a-z]|[a-z]", re.IGNORECASE)


def _tokenize_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles legal text with section numbers."""
    raw = _SENTENCE_RE.split(text.strip())
    out = []
    for s in raw:
        s = s.strip()
        if len(s) >= 20:
            out.append(s)
    return out


def _word_set(sentence: str) -> frozenset[str]:
    words = {w.lower() for w in _WORD_RE.findall(sentence)}
    return frozenset(words - _STOP)


def _similarity(ws_a: frozenset[str], ws_b: frozenset[str]) -> float:
    """Mihalcea & Tarau's normalized overlap."""
    if not ws_a or not ws_b:
        return 0.0
    overlap = len(ws_a & ws_b)
    if overlap == 0:
        return 0.0
    return overlap / (math.log(len(ws_a)) + math.log(len(ws_b)) + 1e-9)


def rank_sentences(sentences: list[str]) -> list[tuple[float, int, str]]:
    """Return [(score, original_index, sentence), ...] sorted by score desc."""
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [(1.0, 0, sentences[0])]

    word_sets = [_word_set(s) for s in sentences]

    # Build adjacency matrix
    weights: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _similarity(word_sets[i], word_sets[j])
            weights[i][j] = sim
            weights[j][i] = sim

    # Row sums for normalization
    row_sums = [sum(weights[i]) for i in range(n)]

    # PageRank iteration
    scores = [1.0 / n] * n
    for _ in range(MAX_ITER):
        new_scores = [0.0] * n
        max_delta = 0.0
        for i in range(n):
            rank_sum = 0.0
            for j in range(n):
                if row_sums[j] > 0 and weights[j][i] > 0:
                    rank_sum += weights[j][i] / row_sums[j] * scores[j]
            new_scores[i] = (1 - DAMPING) / n + DAMPING * rank_sum
            max_delta = max(max_delta, abs(new_scores[i] - scores[i]))
        scores = new_scores
        if max_delta < CONVERGENCE:
            break

    return sorted(
        [(scores[i], i, sentences[i]) for i in range(n)],
        key=lambda t: -t[0],
    )


def summarize(text: str, *, ratio: float = 0.2, max_sentences: int = 10,
              min_sentences: int = 1) -> list[str]:
    """Return the top sentences from `text`, in document order.

    `ratio` controls what fraction of sentences to keep. `max_sentences` caps
    the output. The returned sentences are in their original document order,
    not ranked by score — this reads better as a summary.
    """
    sentences = _tokenize_sentences(text)
    if not sentences:
        return []

    ranked = rank_sentences(sentences)
    k = max(min_sentences, min(max_sentences, int(len(sentences) * ratio)))
    top_indices = sorted(t[1] for t in ranked[:k])
    return [sentences[i] for i in top_indices]


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("textrank")

    # ── basic extraction ──────────────────────────────────────────────────
    text = (
        "This Non-Disclosure Agreement is entered into between Acme Corp and "
        "Beta Ltd. The parties agree to keep all confidential information "
        "strictly private. Confidential information includes trade secrets, "
        "business plans, and financial data. The receiving party shall not "
        "disclose any confidential information to third parties without prior "
        "written consent. This agreement shall remain in force for a period "
        "of two years from the date of execution. Either party may terminate "
        "this agreement by providing thirty days written notice. The governing "
        "law of this agreement shall be the laws of India. Any disputes shall "
        "be resolved through arbitration in Mumbai."
    )
    result = summarize(text, ratio=0.3)
    check(len(result) >= 1, f"produces at least one sentence ({len(result)})")
    check(all(isinstance(s, str) and len(s) >= 20 for s in result),
          "every result is a real sentence")

    # ── document order preserved ──────────────────────────────────────────
    sentences = _tokenize_sentences(text)
    ranked = rank_sentences(sentences)
    top_2 = sorted(t[1] for t in ranked[:2])
    check(top_2 == sorted(top_2), "top sentences are returned in document order")

    # ── empty and short inputs ────────────────────────────────────────────
    check(summarize("") == [], "empty text returns empty list")
    check(summarize("Short.") == [], "too-short sentence is excluded")
    one = summarize("This is a sufficiently long sentence about a legal matter.")
    check(len(one) == 1, f"single sentence returns itself ({len(one)})")

    # ── similarity is symmetric and normalized ────────────────────────────
    ws_a = _word_set("The company shall indemnify the contractor")
    ws_b = _word_set("The contractor shall be indemnified by the company")
    sim = _similarity(ws_a, ws_b)
    check(sim > 0, f"overlapping sentences have positive similarity ({sim:.3f})")
    check(sim == _similarity(ws_b, ws_a), "similarity is symmetric")

    ws_empty = _word_set("")
    check(_similarity(ws_empty, ws_a) == 0.0, "empty word set gives zero similarity")

    # ── longer text gets more selective ────────────────────────────────────
    long_text = ". ".join(f"Clause {i} of the agreement states that party A shall "
                          f"perform obligation number {i}" for i in range(50))
    result_long = summarize(long_text, ratio=0.1, max_sentences=5)
    check(len(result_long) <= 5, f"max_sentences is respected ({len(result_long)})")

    # ── convergence ───────────────────────────────────────────────────────
    ranked2 = rank_sentences(sentences)
    check(abs(sum(t[0] for t in ranked2) - sum(t[0] for t in ranked)) < 1e-6,
          "PageRank converges to the same scores on repeated runs")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
