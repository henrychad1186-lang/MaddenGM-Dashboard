"""Tests for roster module functionality."""

import pytest
from src.roster import (
    _normalize_pos,
    _assign_group,
    _POS_ORDER,
    ovr_color,
    ovr_label,
    _letter_grade,
)


class TestNormalizePos:
    """Tests for position normalization."""

    def test_redg_normalizes_to_edge(self):
        assert _normalize_pos("REDG") == "EDGE"

    def test_ledg_normalizes_to_edge(self):
        assert _normalize_pos("LEDG") == "EDGE"

    def test_lolb_normalizes_to_olb(self):
        assert _normalize_pos("LOLB") == "OLB"

    def test_rolb_normalizes_to_olb(self):
        assert _normalize_pos("ROLB") == "OLB"

    def test_standard_pos_unchanged(self):
        assert _normalize_pos("QB") == "QB"
        assert _normalize_pos("WR") == "WR"
        assert _normalize_pos("CB") == "CB"

    def test_handles_whitespace(self):
        assert _normalize_pos(" rolb ") == "OLB"
        assert _normalize_pos(" LEDG ") == "EDGE"

    def test_case_insensitive(self):
        assert _normalize_pos("lolb") == "OLB"
        assert _normalize_pos("Rolb") == "OLB"
        assert _normalize_pos("redg") == "EDGE"


class TestPosOrder:
    """Tests for position order completeness."""

    def test_fb_in_pos_order(self):
        assert "FB" in _POS_ORDER

    def test_all_standard_positions_present(self):
        expected = {"QB", "HB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT",
                    "EDGE", "DT", "MLB", "OLB", "CB", "SS", "FS"}
        assert expected == set(_POS_ORDER)
