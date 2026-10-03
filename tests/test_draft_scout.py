"""Draft scouting estimates, grade parsing, rules validation and calibration."""

import json

import pandas as pd
import pytest

from src import draft_scout as ds


@pytest.fixture
def rules():
    return ds.default_rules()


# ── Speed ──

@pytest.mark.parametrize("forty, spd", [(4.24, 99), (4.35, 95), (4.43, 92), (4.49, 90)])
def test_speed_reads_the_chart(rules, forty, spd):
    est = ds.estimate_speed(forty, rules)
    assert est["est"] == spd and est["basis"] == "chart"


def test_speed_interpolates_between_chart_points(rules):
    assert ds.estimate_speed(4.445, rules)["est"] in (91, 92)


def test_speed_extrapolates_past_the_chart_and_says_so(rules):
    est = ds.estimate_speed(4.51, rules)
    assert est["basis"] == "extrapolated"
    # Research: a 4.51 lands 87-91, usually 88-89.
    assert 88 <= est["est"] <= 89 and est["low"] >= 86 and est["high"] <= 91


def test_speed_never_exceeds_99(rules):
    assert ds.estimate_speed(4.10, rules)["est"] == 99
    assert ds.estimate_speed(4.10, rules)["high"] == 99


@pytest.mark.parametrize("forty, tier", [
    (4.40, "90+ safe"), (4.43, "90+ safe"), (4.46, "90 coin flip"),
    (4.49, "90 coin flip"), (4.52, "under 90")])
def test_speed_tier_uses_absolute_time(rules, forty, tier):
    assert ds.estimate_speed(forty, rules)["tier"] == tier


@pytest.mark.parametrize("bad", [None, "", "fast", float("nan"), 0, -4.4])
def test_speed_ignores_missing_or_bad_times(rules, bad):
    assert ds.estimate_speed(bad, rules) is None


# ── Agility / COD ──

def test_three_cone_maps_6_60_to_99_and_6_83_to_90(rules):
    assert ds.estimate_agility(6.60, rules)["est"] == 99
    assert ds.estimate_agility(6.83, rules)["est"] == 90


def test_sub_7_three_cone_is_not_elite_agility(rules):
    est = ds.estimate_agility(6.99, rules)
    assert est["est"] < 90 and est["basis"] == "extrapolated"


def test_shuttle_anchor_splits_evenly_without_a_three_cone(rules):
    est = ds.estimate_cod(4.17, None, rules)
    assert est["total"] == 178 and est["est"] == 89 and est["basis"] == "anchor"


def test_shuttle_cod_is_total_minus_three_cone_agility(rules):
    # Same shuttle, higher Agility -> less COD.
    assert ds.estimate_cod(4.17, 93, rules)["est"] == 85


def test_slower_shuttle_means_less_cod(rules):
    assert ds.estimate_cod(4.30, None, rules)["est"] < ds.estimate_cod(4.17, None, rules)["est"]


# ── Strength ──

def test_bench_anchor_reproduces_the_research_point(rules):
    assert ds.estimate_strength(38, 32, rules)["est"] == 97


def test_longer_arms_make_the_same_reps_worth_more(rules):
    short = ds.estimate_strength(30, 31, rules)["est"]
    long_ = ds.estimate_strength(30, 35, rules)["est"]
    assert long_ > short


def test_bench_without_arm_length_is_flagged(rules):
    assert "no arm length" in ds.estimate_strength(30, None, rules)["basis"]


# ── Grades ──

def test_a_minus_is_the_confirmed_range(rules):
    assert ds.grade_range("A-", rules) == {"low": 82, "high": 85, "confirmed": True}


@pytest.mark.parametrize("text", ["A to C", "A-C", "a~c", "A / C", "A..C", "A–C"])
def test_scouted_ranges_span_both_ends(rules, text):
    r = ds.grade_range(text, rules)
    assert (r["low"], r["high"]) == (62, 89)


def test_double_hyphen_reads_as_a_minus_to_c(rules):
    assert ds.grade_range("A--C", rules)["high"] == 85


@pytest.mark.parametrize("bad", ["", "Z", "A to B to C", "E", None])
def test_unreadable_grades_return_none(rules, bad):
    assert ds.grade_range(bad, rules) is None


def test_parse_grades_accepts_colon_equals_and_separators():
    assert ds.parse_grades("mcv:A-; PRS = A to C, zcv:B\nnoise") == {
        "MCV": "A-", "PRS": "A to C", "ZCV": "B"}


# ── Evaluation ──

def _board(rows):
    return ds.clean_board(pd.DataFrame(rows))


def test_a_tier_core_reveal_is_scout_now(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "MLB", "Grades": "PUR:A; TAK:B"}, rules)
    assert ev["Priority"] == "Scout now" and ev["A_Tier_Core"] == "PUR"


def test_range_that_could_be_a_tier_asks_to_narrow(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "CB", "Grades": "MCV:A to C"}, rules)
    assert ev["Priority"] == "Narrow grades" and ev["Maybe_A_Tier"] == "MCV"


def test_non_core_a_grade_does_not_raise_priority(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "CB", "Grades": "TRK:A+; MCV:C"}, rules)
    assert ev["Priority"] == "Low"


def test_no_grades_is_unscouted(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "CB", "Forty": 4.40}, rules)
    assert ev["Priority"] == "Unscouted" and ev["SPD"] == 93


def test_side_labels_fold_to_the_core_position(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "rolb", "Grades": "PUR:A"}, rules)
    assert ev["Pos"] == "OLB" and ev["Priority"] == "Scout now"


def test_slow_corner_is_flagged(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "CB", "Forty": 4.60}, rules)
    assert "sub-90 speed" in ev["Flags"]


def test_bad_grade_is_flagged_not_fatal(rules):
    ev = ds.evaluate_prospect({"Name": "X", "Pos": "CB", "Grades": "MCV:Q"}, rules)
    assert "MCV:Q" in ev["Flags"]


def test_core_fit_mixes_grades_and_combine(rules):
    ev = ds.evaluate_prospect(
        {"Name": "X", "Pos": "CB", "Forty": 4.49, "Grades": "MCV:A-"}, rules)
    assert ev["Core_Fit"] == pytest.approx((90 + 83.5) / 2, abs=0.05)
    assert ev["Core_Known"] == "2/5"


def test_board_sorts_scouting_targets_first(rules):
    out = ds.evaluate_board(_board([
        {"Name": "Low", "Pos": "CB", "Grades": "MCV:C"},
        {"Name": "Top", "Pos": "CB", "Grades": "MCV:A"},
        {"Name": "Maybe", "Pos": "CB", "Grades": "MCV:A to C"},
    ]), rules)
    assert out["Name"].tolist() == ["Top", "Maybe", "Low"]


def test_empty_board_evaluates_to_empty(rules):
    assert ds.evaluate_board(ds.empty_board(), rules).empty


# ── Board I/O ──

def test_clean_board_adds_columns_coerces_numbers_and_drops_blank_names():
    b = ds.clean_board(pd.DataFrame([
        {"Name": "A", "Forty": "4.41", "Extra": 1},
        {"Name": "", "Forty": 4.5},
        {"Name": "B", "Forty": "fast"},
    ]))
    assert list(b.columns[:len(ds.PROSPECT_COLUMNS)]) == ds.PROSPECT_COLUMNS
    assert b["Name"].tolist() == ["A", "B"]
    assert b["Forty"].iloc[0] == 4.41 and pd.isna(b["Forty"].iloc[1])
    assert "Extra" in b.columns


def test_board_round_trips_through_csv(tmp_path):
    path = tmp_path / "b.csv"
    board = ds.clean_board(pd.DataFrame([{"Name": "A", "Pos": "CB", "Forty": 4.4,
                                          "Grades": "MCV:A-; PRS:B to A"}]))
    assert ds.save_board(board, str(path))
    back = ds.load_board(str(path))
    assert back.loc[0, "Grades"] == "MCV:A-; PRS:B to A" and back.loc[0, "Forty"] == 4.4


def test_missing_or_corrupt_board_is_empty(tmp_path):
    assert ds.load_board(str(tmp_path / "nope.csv")).empty
    bad = tmp_path / "bad.csv"
    bad.write_text("")
    assert ds.load_board(str(bad)).empty


# ── Rules ──

def test_defaults_are_a_copy():
    r = ds.default_rules()
    r["speed_chart"].clear()
    assert ds.DEFAULT_RULES["speed_chart"]


def test_clean_rules_keeps_good_keys_and_drops_bad_ones():
    r = ds.clean_rules({
        "speed_band": 3,
        "speed_chart": "nonsense",
        "three_cone": {"fast": 6.5, "slow": "x"},
        "grades": [{"grade": "a", "low": 85, "high": 99}, {"grade": "Z", "low": 1, "high": 2},
                   {"grade": "B", "low": 90, "high": 80}],
        "core_attrs": {"rolb": ["pur", " tak ", ""], "CB": "MCV"},
    })
    assert r["speed_band"] == 3
    assert r["speed_chart"] == ds.DEFAULT_RULES["speed_chart"]
    assert r["three_cone"]["fast"] == 6.5 and r["three_cone"]["slow"] == 6.83
    assert [g["grade"] for g in r["grades"]] == ["A"]
    assert r["core_attrs"] == {"OLB": ["PUR", "TAK"]}


def test_clean_rules_rejects_a_zero_width_three_cone():
    r = ds.clean_rules({"three_cone": {"fast": 6.7, "slow": 6.7}})
    assert r["three_cone"] == ds.DEFAULT_RULES["three_cone"]


def test_clean_rules_rejects_a_one_point_speed_chart():
    r = ds.clean_rules({"speed_chart": [[4.4, 93], [4.4, 92]]})
    assert r["speed_chart"] == ds.DEFAULT_RULES["speed_chart"]


@pytest.mark.parametrize("raw", [None, [], "x", 5])
def test_clean_rules_on_non_dict_returns_defaults(raw):
    assert ds.clean_rules(raw) == ds.default_rules()


def test_rules_round_trip_and_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "r.json"
    r = ds.default_rules()
    r["speed_band"] = 3.0
    assert ds.save_rules(r, str(path))
    assert ds.load_rules(str(path))["speed_band"] == 3.0
    path.write_text("{not json")
    assert ds.load_rules(str(path)) == ds.default_rules()


def test_rules_are_json_serialisable():
    json.dumps(ds.default_rules())


# ── Calibration ──

def test_calibration_reports_bias_per_rating(rules):
    board = _board([
        {"Name": "A", "Pos": "CB", "Forty": 4.43, "Actual_SPD": 94},   # est 92, +2
        {"Name": "B", "Pos": "CB", "Forty": 4.49, "Actual_SPD": 94},   # est 90, +4
        {"Name": "C", "Pos": "DT", "Bench": 38, "Arm_In": 32},          # no actual
    ])
    cal = ds.calibrate(board, rules).set_index("Rating")
    assert list(cal.index) == ["SPD"]
    assert cal.loc["SPD", "Players"] == 2
    assert cal.loc["SPD", "Mean_Error"] == 3.0
    assert cal.loc["SPD", "Within_2"] == "50%"


def test_calibration_without_actuals_is_empty(rules):
    assert ds.calibrate(_board([{"Name": "A", "Forty": 4.4}]), rules).empty
