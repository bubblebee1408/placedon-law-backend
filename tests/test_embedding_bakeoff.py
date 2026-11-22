"""Tests for the embedding bake-off harness (structural only — no model downloads)."""
from __future__ import annotations

import pytest


def test_self_test():
    """The bake-off module's own self-test passes."""
    from eval.embedding_bakeoff import _test
    assert _test() == 0


def test_candidates_declared():
    from eval.embedding_bakeoff import CANDIDATES, INCUMBENT
    assert len(CANDIDATES) >= 2
    assert INCUMBENT == "sentence-transformers/all-MiniLM-L6-v2"


def test_rrf_formula():
    from eval.embedding_bakeoff import _rrf
    r = _rrf([{"a": 1, "b": 2}, {"b": 1, "c": 3}], k=60)
    assert abs(r["a"] - 1 / 61) < 1e-9
    assert abs(r["b"] - (1 / 62 + 1 / 61)) < 1e-9
    assert abs(r["c"] - 1 / 63) < 1e-9


def test_rank_map():
    from eval.embedding_bakeoff import _rank_map
    hits = [("s1", "Title1", 0.9), ("s2", "Title2", 0.8), ("s1", "Title1", 0.7)]
    rm = _rank_map(hits)
    assert rm["s1"] == 1  # first occurrence wins
    assert rm["s2"] == 2


def test_safe_name():
    from eval.embedding_bakeoff import _safe_name
    assert _safe_name("law-ai/InLegalBERT") == "law_ai_InLegalBERT"
    assert _safe_name("BAAI/bge-m3") == "BAAI_bge_m3"


def test_bakeoff_result_frozen():
    from eval.embedding_bakeoff import BakeoffResult
    r = BakeoffResult(
        model="test", dense_p1=0.5, dense_r5=0.8,
        fusion_p1=0.6, fusion_r5=0.9,
        incumbent_fusion_p1=0.8, incumbent_fusion_r5=0.97,
        ci_candidate={"mean": 0.6, "lo": 0.5, "hi": 0.7, "reliable": True},
        ci_incumbent={"mean": 0.8, "lo": 0.7, "hi": 0.9, "reliable": True},
        ci_overlap=True, wins=False, n=70,
    )
    with pytest.raises(AttributeError):
        r.model = "other"
