"""Tests for the reranker bake-off harness (structural only — no model downloads)."""
from __future__ import annotations

import pytest


def test_self_test():
    from eval.reranker_bakeoff import _test
    assert _test() == 0


def test_features_8():
    from eval.reranker_bakeoff import FEATURES_8
    from checker.reranker import FEATURES
    assert len(FEATURES_8) == 8
    assert FEATURES_8[:7] == FEATURES
    assert FEATURES_8[7] == "cross_encoder"
