"""Tests for roster module functionality."""

from src.roster import (
    _normalize_pos,
    _POS_ORDER,
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
        expected = ["QB", "HB", "FB", "WR", "TE", "LT", "LG", "C", "RG", "RT",
                    "EDGE", "DT", "MLB", "OLB", "CB", "SS", "FS"]
        assert list(_POS_ORDER) == expected


class TestLetterGrade:
    """Tests for calibrated Madden NFL letter grades."""

    def test_elite_grades(self):
        from src.roster import _letter_grade
        assert _letter_grade(96.0) == "A+"
        assert _letter_grade(93.0) == "A+"
        assert _letter_grade(91.0) == "A"
        assert _letter_grade(88.0) == "A"
        assert _letter_grade(86.5) == "A-"
        assert _letter_grade(85.0) == "A-"

    def test_starter_grades(self):
        from src.roster import _letter_grade
        assert _letter_grade(84.0) == "B+"
        assert _letter_grade(82.0) == "B+"
        assert _letter_grade(80.5) == "B"
        assert _letter_grade(78.0) == "B"
        assert _letter_grade(76.5) == "B-"
        assert _letter_grade(75.0) == "B-"

    def test_low_and_sub_replacement_grades(self):
        from src.roster import _letter_grade
        assert _letter_grade(73.0) == "C+"
        assert _letter_grade(70.0) == "C"
        assert _letter_grade(66.5) == "C-"
        assert _letter_grade(62.0) == "D"
        assert _letter_grade(55.0) == "F"


class TestCalculatePositionRating:
    """Tests for depth-weighted room ratings."""

    def test_single_player_returns_ovr(self):
        from src.roster import _calculate_position_rating
        assert _calculate_position_rating("QB", [86]) == 86.0

    def test_one_starter_weights_starter_heavily(self):
        from src.roster import _calculate_position_rating
        # 95 starter + 65 backup -> 0.78 * 95 + 0.22 * 65 = 74.1 + 14.3 = 88.4
        rating = _calculate_position_rating("QB", [95, 65])
        assert round(rating, 1) == 88.4

    def test_edge_two_starter_weighting(self):
        from src.roster import _calculate_position_rating
        # Parsons (98) + Dennis-Sutton (77) + Van Ness (76) + Oliver (72) + Sorrell (71)
        rating = _calculate_position_rating("EDGE", [98, 77, 76, 72, 71])
        assert rating >= 85.0  # Must reflect an A-caliber room

    def test_wr_three_starter_weighting(self):
        from src.roster import _calculate_position_rating
        rating = _calculate_position_rating("WR", [80, 78, 78, 74, 73, 72])
        assert 77.0 <= rating <= 79.5

