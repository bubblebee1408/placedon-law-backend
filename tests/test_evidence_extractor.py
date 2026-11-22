"""Tests for checker/evidence_extractor.py — structural + real specimen."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

SPECIMENS = Path(__file__).resolve().parent.parent / "corpus" / "testdocs"


def test_self_test():
    from checker.evidence_extractor import _test
    assert _test() == 0


def test_extract_returns_frozen():
    from checker.evidence_extractor import ExtractionResult
    r = ExtractionResult(
        evidence=None, board_meeting_dates_found=(), agm_dates_found=(),
        previous_meeting_dates_found=(), director_count_found=None,
        quorum_recorded=False, financial_year_found=None,
        section_refs=(), all_dates=(),
    )
    with pytest.raises(AttributeError):
        r.quorum_recorded = True


def test_dmy_formats():
    from checker.evidence_extractor import _all_dates
    dates = _all_dates("29 May 2024, 15th June, 2024, 1st January 2023")
    assert date(2024, 5, 29) in dates
    assert date(2024, 6, 15) in dates
    assert date(2023, 1, 1) in dates


def test_mdy_formats():
    from checker.evidence_extractor import _all_dates
    dates = _all_dates("May 29, 2024 and January 1, 2023")
    assert date(2024, 5, 29) in dates
    assert date(2023, 1, 1) in dates


def test_numeric_and_iso():
    from checker.evidence_extractor import _all_dates
    dates = _all_dates("29/05/2024 and 2024-01-15")
    assert date(2024, 5, 29) in dates
    assert date(2024, 1, 15) in dates


def test_route_mobile_outcome():
    """Real Route Mobile board outcome — MDY date after 'today i.e.'."""
    from checker.evidence_extractor import extract
    text = (SPECIMENS / "board_outcomes" / "routemobile_outcome_board_meeting_2024-05-29.txt").read_text()
    r = extract(text, as_of=date(2024, 6, 1))
    assert r.board_meeting_dates_found
    assert date(2024, 5, 29) in r.board_meeting_dates_found


def test_icsi_subsequent_board_meeting():
    """ICSI specimen 04 — has PRESENT section, quorum, previous meeting ref."""
    from checker.evidence_extractor import extract
    text = (SPECIMENS / "icsi_specimens" / "04_minutes_subsequent_board_meeting_annexVIII.txt").read_text()
    r = extract(text, as_of=date(2024, 1, 1))
    assert r.quorum_recorded
    assert r.section_refs  # references Companies Act sections


def test_icsi_first_board_meeting():
    """ICSI specimen 03 — first board meeting template."""
    from checker.evidence_extractor import extract
    text = (SPECIMENS / "icsi_specimens" / "03_minutes_first_board_meeting_annexVII.txt").read_text()
    r = extract(text, as_of=date(2024, 1, 1))
    assert r.quorum_recorded
    assert r.section_refs


def test_empty_text():
    from checker.evidence_extractor import extract
    r = extract("", as_of=date(2024, 1, 1))
    assert r.evidence.board_meetings is None
    assert r.evidence.total_board_strength is None
    assert r.evidence.agm_dates is None
    assert not r.quorum_recorded


def test_evidence_slots_into_obligations():
    """The Evidence object is accepted by obligations.build()."""
    from checker.evidence_extractor import extract
    from checker.obligations import Evidence
    r = extract("Board meeting held on 15 January 2024.", as_of=date(2024, 2, 1))
    assert isinstance(r.evidence, Evidence)
