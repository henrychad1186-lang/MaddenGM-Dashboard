"""
Tests for dynasty history loading.

`load_history` used to return `SAMPLE_HISTORY` whenever no history file
existed, so a franchise that had archived nothing opened the Dynasty tab
to three seasons it never played — a 2025 Super Bowl win among them —
rendered in the same styling as real archived seasons.
"""

import json

import pytest

from src import dynasty


@pytest.fixture
def history_file(tmp_path, monkeypatch):
    """Point the module at a throwaway history path."""
    path = tmp_path / "dynasty_history.json"
    monkeypatch.setattr(dynasty, "_HISTORY_FILE", str(path))
    return path


def _season(**overrides):
    season = {
        "season": 2027, "era": "The Rebuild", "record": "11-6",
        "wins": 11, "losses": 6, "playoff_result": "Divisional Round",
        "mvp": "J. Love", "mvp_stats": "4,000 Yds",
        "top_rusher": "J. Jacobs", "rush_yards": 1100,
        "top_receiver": "J. Reed", "rec_yards": 1200, "notes": "",
    }
    season.update(overrides)
    return season


class TestLoadHistory:

    def test_no_file_is_no_history(self, history_file):
        assert dynasty.load_history() == []

    def test_does_not_return_the_sample_seasons(self, history_file):
        # The specific regression: "The Jordan Love Era" presented as the
        # user's own franchise record.
        assert dynasty.load_history() != dynasty.SAMPLE_HISTORY
        assert not any(s.get("era") == "The Jordan Love Era"
                       for s in dynasty.load_history())

    def test_reads_what_was_archived(self, history_file):
        history_file.write_text(json.dumps([_season()]))
        loaded = dynasty.load_history()
        assert len(loaded) == 1
        assert loaded[0]["era"] == "The Rebuild"

    def test_corrupt_file_is_empty_not_a_crash(self, history_file):
        history_file.write_text("{not json")
        assert dynasty.load_history() == []

    def test_a_json_object_is_not_history(self, history_file):
        # Valid JSON of the wrong shape used to be handed straight to the
        # tab, which iterates it as a list of seasons.
        history_file.write_text(json.dumps({"season": 2027}))
        assert dynasty.load_history() == []


class TestCareerLeaders:

    def test_empty_history_returns_an_empty_frame(self):
        # Previously raised KeyError('Rush Yds'), which is what the tab
        # would now hit on every fresh franchise.
        leaders = dynasty.get_career_leaders([])
        assert leaders.empty
        assert "Total Yds" in leaders.columns

    def test_aggregates_across_seasons(self):
        leaders = dynasty.get_career_leaders([
            _season(season=2027, rush_yards=1100),
            _season(season=2028, rush_yards=900),
        ])
        jacobs = leaders[leaders["Player"] == "J. Jacobs"].iloc[0]
        assert jacobs["Rush Yds"] == 2000


class TestArchiveSeason:

    def test_archiving_the_first_season_starts_from_empty(self, history_file):
        # Not from the sample seasons: appending to those would put three
        # fabricated years permanently into the user's saved history.
        history = dynasty.archive_season(_season(), dynasty.load_history())
        assert len(history) == 1
        assert history[0]["season"] == 2027
        assert json.loads(history_file.read_text())[0]["season"] == 2027

    def test_a_repeat_season_updates_rather_than_duplicates(self,
                                                            history_file):
        dynasty.archive_season(_season(), [])
        history = dynasty.archive_season(
            _season(record="13-4", wins=13), dynasty.load_history())
        assert len(history) == 1
        assert history[0]["record"] == "13-4"

    def test_seasons_are_kept_in_order(self, history_file):
        dynasty.archive_season(_season(season=2029), [])
        history = dynasty.archive_season(
            _season(season=2027), dynasty.load_history())
        assert [s["season"] for s in history] == [2027, 2029]


class TestGetEras:

    def test_empty_history_has_no_eras(self):
        assert dynasty.get_eras([]) == []

    def test_deduplicates_preserving_order(self):
        eras = dynasty.get_eras([
            _season(season=2027, era="A"),
            _season(season=2028, era="B"),
            _season(season=2029, era="A"),
        ])
        assert eras == ["A", "B"]
