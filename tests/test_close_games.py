"""Tests for the close-game split behind the Home panel and GM Chat."""

import pandas as pd
import pytest

from src import close_games


def _log():
    # diffs: +3 W, -3 L, -7 L, +20 W, +14 W, 0 T
    return pd.DataFrame({
        "Result": ["WIN", "LOSS", "LOSS", "WIN", "WIN", "TIE"],
        "Points_For": [24, 21, 20, 34, 28, 17],
        "Points_Against": [21, 24, 27, 14, 14, 17],
        "Turnovers": [1, 2, 2, 0, 0, 1],
        "Takeaways": [1, 0, 1, 2, 3, 1],
        "Sacks_For": [2, 2, 2, 2, 2, 2],
    })


def test_split_records_and_margin_buckets():
    r = close_games.analyze(_log())
    assert r["close"]["record"] == "1-2-1"
    assert r["decided"]["record"] == "2-0"
    assert r["fg"]["record"] == "1-1-1"          # +3, -3, 0
    assert r["one_score_4_8"]["record"] == "0-1"  # -7
    assert r["close"]["win_pct"] == pytest.approx(37.5)  # tie = half a win


def test_score_diff_used_when_present():
    df = _log().drop(columns=["Points_For", "Points_Against"])
    df["Score_Diff"] = [3, -3, -7, 20, 14, 0]
    assert close_games.analyze(df)["close"]["games"] == 4


def test_drivers_are_worse_stats_only_and_exclude_points():
    r = close_games.analyze(_log())
    labels = [d["label"] for d in r["drivers"]]
    # 1.5 vs 0 turnovers (gap over a floor of 1.0) outranks 0.75 vs 2.5 takeaways
    assert labels == ["Turnovers", "Takeaways"]
    assert "Sacks" not in labels            # identical
    assert not {"Points scored", "Points allowed", "Turnover margin"} & set(labels)
    tm = next(x for x in r["rows"] if x["label"] == "Turnover margin")
    assert tm["close"] == pytest.approx(-0.75) and tm["decided"] == pytest.approx(2.5)


def test_missing_optional_columns_drop_their_rows():
    df = _log()[["Result", "Points_For", "Points_Against"]]
    r = close_games.analyze(df)
    assert [x["label"] for x in r["rows"]] == ["Points scored", "Points allowed"]
    assert r["drivers"] == []


def test_nothing_to_split_returns_none():
    assert close_games.analyze(None) is None
    assert close_games.analyze(pd.DataFrame()) is None
    assert close_games.analyze(pd.DataFrame({"Result": ["WIN"]})) is None


def test_summary_lines_for_chat():
    lines = close_games.summary_lines(close_games.analyze(_log()))
    assert "Close games (<= 8 pts): 1-2-1 vs 2-0" in lines[0]
    assert "Decided by <= 3: 1-1-1; by 4-8: 0-1" in lines[1]
    assert close_games.summary_lines(None) == []


def test_shipped_log_close_record():
    df = pd.read_csv("data/game_logs.csv")
    df["Result"] = df["Result"].map({"W": "WIN", "L": "LOSS", "T": "TIE"})
    r = close_games.analyze(df)
    assert r["close"]["record"] == "4-9"
    assert r["decided"]["record"] == "13-4"


class TestNoUnreadSplitRates:
    """`_group_stats` carried third_down_pct / rz_td_pct that nothing read.

    On the shipped log those were built from one game per side — 20.0%
    close vs 100.0% decided — and sat on the dict looking authoritative.
    Nothing rendered them, so they were a loaded gun for whoever did.
    Either the sample size travels with a rate or the rate goes.
    """

    # Spelled out rather than derived from the key: efficiency_rates
    # pairs third_down_pct with third_down_games but rz_td_pct with
    # rz_games, and renaming a published key to make a test tidier is
    # the wrong way round.
    _COUNT_FOR = {"third_down_pct": "third_down_games",
                  "rz_td_pct": "rz_games"}

    def test_a_rate_is_never_published_without_its_sample_size(self):
        df = pd.read_csv("data/game_logs.csv")
        df["Result"] = df["Result"].map({"W": "WIN", "L": "LOSS", "T": "TIE"})
        result = close_games.analyze(df)
        for side in ("close", "decided"):
            rates = [k for k in result[side]
                     if k.endswith("_pct") and k != "win_pct"]
            assert rates, f"{side} publishes no rates; did they move?"
            for key in rates:
                assert key in self._COUNT_FOR, (
                    f"{side}.{key} is a new rate — pair it with a count")
                assert self._COUNT_FOR[key] in result[side], (
                    f"{side}.{key} is published without a game count")


class TestRecordReadsEitherSpelling:
    """`derive_fields` writes "W"; `app._prepare_game_log` expands it to
    "WIN" before the panel sees it. record() matched only the long form,
    so a caller that skipped that normalisation got a silent 0-0 rather
    than an error — which is exactly how a reader gets fooled."""

    @pytest.mark.parametrize("spelling", [
        ["W", "W", "L"], ["WIN", "WIN", "LOSS"], ["win", "Win", "loss"],
    ])
    def test_short_and_long_forms_agree(self, spelling):
        df = pd.DataFrame({"Result": spelling})
        rec = close_games.record(df)
        assert (rec["wins"], rec["losses"]) == (2, 1), rec

    def test_a_tie_is_still_a_tie_either_way(self):
        assert close_games.record(
            pd.DataFrame({"Result": ["T"]}))["ties"] == 1
        assert close_games.record(
            pd.DataFrame({"Result": ["TIE"]}))["ties"] == 1
