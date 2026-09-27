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
    assert r["close"]["record"] == "4-8"
    assert r["decided"]["record"] == "12-4"
