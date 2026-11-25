"""Tests for checker/document_audit.py — orchestrator + real specimens."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from checker.company_profile import CompanyProfile
from checker.document_audit import AuditReport, audit

SPECIMENS = Path(__file__).resolve().parent.parent / "corpus" / "testdocs"

# A generic private company profile for testing
_PRIVATE = CompanyProfile(
    company_class="private",
    incorporation_date=date(2018, 6, 1),
    as_of=date(2024, 6, 1),
    director_count=5,
)

_LISTED_PUBLIC = CompanyProfile(
    company_class="public",
    incorporation_date=date(2010, 1, 1),
    as_of=date(2024, 6, 1),
    is_listed=True,
    director_count=8,
)


def test_self_test():
    from checker.document_audit import _test
    assert _test() == 0


def test_audit_report_frozen():
    r = audit("Board meeting held on 15 January 2024.", _PRIVATE, as_of=date(2024, 2, 1))
    with pytest.raises(AttributeError):
        r.verdict = "VERIFIED"


class TestRealSpecimens:
    """Run the full audit pipeline on real filed documents."""

    def test_route_mobile_2024_05(self):
        text = (SPECIMENS / "board_outcomes" / "routemobile_outcome_board_meeting_2024-05-29.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2024, 6, 1))
        assert r.extraction.board_meeting_dates_found
        assert date(2024, 5, 29) in r.extraction.board_meeting_dates_found
        assert len(r.obligation_rows) > 0
        assert r.verdict in ("VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "POTENTIAL_ISSUE")

    def test_route_mobile_2025_01(self):
        text = (SPECIMENS / "board_outcomes" / "routemobile_outcome_board_meeting_2025-01-28.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2025, 2, 1))
        assert r.extraction.board_meeting_dates_found
        assert r.extraction.financial_year_found == "2024-25"
        assert len(r.obligation_rows) > 0

    def test_route_mobile_2025_11(self):
        text = (SPECIMENS / "board_outcomes" / "routemobile_outcome_board_meeting_2025-11-03.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2025, 12, 1))
        assert r.extraction.board_meeting_dates_found

    def test_route_mobile_2026_05(self):
        text = (SPECIMENS / "board_outcomes" / "routemobile_outcome_board_meeting_2026-05-07.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2026, 6, 1))
        assert len(r.extraction.board_meeting_dates_found) >= 1

    def test_sonata_agm_2025(self):
        text = (SPECIMENS / "board_outcomes" / "sonata_outcome_of_agm_2025.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2025, 8, 1))
        assert r.extraction.agm_dates_found
        assert date(2025, 7, 31) in r.extraction.agm_dates_found

    def test_sonata_agm_2026(self):
        text = (SPECIMENS / "board_outcomes" / "sonata_outcome_of_agm_2026.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2026, 8, 1))
        assert r.extraction.agm_dates_found

    def test_icsi_first_board(self):
        text = (SPECIMENS / "icsi_specimens" / "03_minutes_first_board_meeting_annexVII.txt").read_text()
        r = audit(text, _PRIVATE, as_of=date(2024, 1, 1))
        assert r.ss_doc_type == "minutes"
        assert r.extraction.quorum_recorded
        assert len(r.ss_findings) > 0  # template text should trigger some SS checks

    def test_icsi_subsequent_board(self):
        text = (SPECIMENS / "icsi_specimens" / "04_minutes_subsequent_board_meeting_annexVIII.txt").read_text()
        r = audit(text, _PRIVATE, as_of=date(2024, 1, 1))
        assert r.ss_doc_type == "minutes"
        assert r.extraction.quorum_recorded

    def test_tata_elxsi_ss_statement(self):
        text = (SPECIMENS / "board_outcomes" / "tataelxsi_board_report_ss_statement_2025_26.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2026, 8, 1))
        assert r.extraction.financial_year_found == "2025-26"

    def test_tcpl_ss_statement(self):
        text = (SPECIMENS / "board_outcomes" / "tcpl_board_report_ss_statement_2025_26.txt").read_text()
        r = audit(text, _LISTED_PUBLIC, as_of=date(2026, 8, 1))
        assert r.extraction.financial_year_found == "2025-26"


class TestPageBoundaries:
    """D-002 phase 2: page_boundaries threads through to SS findings."""

    def test_pages_produce_page_numbers_in_findings(self):
        from checker.pdf_pages import page_boundaries
        page1 = "Minutes of the meeting of the Board of Directors held on 15th January, 2024."
        page2 = (
            "\nPRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\n\n"
            "IN ATTENDANCE\nSecretary\n"
            "The quorum was present.\n"
            "Place: Bengaluru\n"
        )
        pages = [page1, page2]
        text = "\n".join(pages)
        bounds = tuple(page_boundaries(pages))
        r = audit(text, _PRIVATE, as_of=date(2024, 2, 1), page_boundaries=bounds)
        paged = [f for f in r.ss_findings if f.page is not None]
        assert len(paged) > 0, "at least one finding should have a page number"
        assert any(f.page == 1 for f in paged), "page2 content should anchor to page index 1"


class TestVerdictLogic:
    """Unit tests for verdict derivation."""

    def test_unknown_class_is_unverified(self):
        r = audit("Random unclassifiable text.", _PRIVATE, as_of=date(2024, 1, 1))
        assert r.verdict == "UNVERIFIED"

    def test_board_minutes_with_evidence(self):
        text = (
            "Minutes of the meeting of the Board of Directors held on 15th January, 2024.\n"
            "PRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\n\n"
            "IN ATTENDANCE\nSecretary\n"
            "The quorum was present.\n"
            "Section 173 of the Companies Act, 2013.\n"
        )
        r = audit(text, _PRIVATE, as_of=date(2024, 2, 1))
        assert r.doc_class == "board_minutes"
        assert len(r.obligation_rows) > 0
