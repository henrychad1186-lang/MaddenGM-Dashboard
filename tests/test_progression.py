"""Tests for the progression log reader/writer."""

import pytest

from src import progression, roster


@pytest.fixture
def prog_csv(tmp_path, monkeypatch):
    path = tmp_path / "progression_log.csv"
    monkeypatch.setattr(progression, "_PROG_CSV", str(path))
    return path


def test_missing_log_is_empty(prog_csv):
    assert progression.get_progression("GB").empty
    assert progression.get_movers("GB") == {"gainers": [], "losers": []}


@pytest.mark.parametrize("content", ["", "garbage\x00\x01", "a,b\n1,2\n"])
def test_unreadable_log_is_empty_not_a_crash(prog_csv, content):
    prog_csv.write_text(content)
    assert progression.get_progression("GB").empty


def test_snapshot_replaces_a_corrupt_log(prog_csv):
    prog_csv.write_text("")
    team = roster.TEAMS[0]
    saved = progression.snapshot_roster(team, 2026, 1)
    assert saved == len(roster.get_roster(team))
    assert len(progression.get_progression(team)) == saved


def test_movers_between_snapshots(prog_csv):
    prog_csv.write_text(
        "Name,Pos,Team,Season,Week,OVR\n"
        "A,QB,GB,2026,1,80\nA,QB,GB,2026,2,84\n"
        "B,WR,GB,2026,1,75\nB,WR,GB,2026,2,72\n")
    movers = progression.get_movers("GB")
    assert movers["gainers"] == [{"Name": "A", "Pos": "QB", "Start_OVR": 80,
                                  "Current_OVR": 84, "Delta": 4}]
    assert movers["losers"][0]["Delta"] == -3
