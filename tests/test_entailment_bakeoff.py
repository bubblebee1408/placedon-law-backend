"""Tests for the entailment bake-off harness (structural only — no model downloads)."""
from __future__ import annotations

import pytest


def test_self_test():
    from eval.entailment_bakeoff import _test
    assert _test() == 0


def test_load_pairs():
    from eval.entailment_bakeoff import _load_pairs
    pairs = _load_pairs()
    assert len(pairs) == 67
    assert all(p.source_span for p in pairs)


def test_incumbent_scores():
    from eval.entailment_bakeoff import _load_pairs, _incumbent_scores
    pairs = _load_pairs()
    scores = _incumbent_scores(pairs)
    assert len(scores) == 67
    assert all(s in (0, 1) for s in scores)
    assert sum(scores) / len(scores) > 0.5
