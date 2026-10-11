"""
The Madden 27 playbook and scheme catalogue, and the saved setup.

The catalogue is a seed the user extends, not a closed list. These
tests pin that: the league is complete and exact, the alternates are
openly partial, and anything the user adds survives alongside them.
"""

import json

import pytest

from src import playbooks


class TestTheLeagueIsComplete:
    """The 32 team books are the one part that can be exact."""

    def test_there_are_thirty_two(self):
        assert len(playbooks.TEAM_PLAYBOOKS) == 32

    def test_no_duplicates(self):
        assert len(set(playbooks.TEAM_PLAYBOOKS)) == 32

    def test_every_entry_is_a_full_team_name(self):
        # "Packers" or "GB" would not match the in-game playbook name.
        for name in playbooks.TEAM_PLAYBOOKS:
            assert " " in name, name

    def test_the_franchise_team_is_in_it(self):
        assert "Green Bay Packers" in playbooks.TEAM_PLAYBOOKS


class TestTheCatalogueAdmitsItIsPartial:
    """The alternates are sourced from community databases and are
    incomplete. The app must say so rather than imply a full list."""

    def test_the_note_says_the_list_is_incomplete(self):
        assert "incomplete" in playbooks.CATALOGUE_NOTE.lower()

    def test_the_note_is_shown_somewhere(self):
        import pathlib
        app = pathlib.Path(__file__).resolve().parent.parent / "app.py"
        assert "CATALOGUE_NOTE" in app.read_text(encoding="utf-8"), (
            "the provenance note must reach the screen, not just the module")

    @pytest.mark.parametrize("names", [
        playbooks.ALTERNATE_OFFENSE, playbooks.ALTERNATE_DEFENSE,
        playbooks.OFFENSIVE_SCHEMES, playbooks.DEFENSIVE_SCHEMES,
    ])
    def test_no_duplicates_and_no_blanks(self, names):
        assert names, "an empty list would offer the user nothing"
        assert len(set(names)) == len(names)
        assert all(n and n == n.strip() for n in names)


class TestOptions:

    def test_builtins_come_through(self):
        assert playbooks.options(["B", "A"]) == ["A", "B"]

    def test_user_entries_are_added(self):
        assert playbooks.options(["A"], ["Z"]) == ["A", "Z"]

    def test_a_differently_cased_duplicate_does_not_double_up(self):
        # "west coast" and "West Coast" are one book, and the built-in
        # spelling is the one that survives.
        out = playbooks.options(["West Coast"], ["west coast"])
        assert out == ["West Coast"]

    def test_blanks_and_non_strings_are_ignored(self):
        assert playbooks.options(["A"], ["", "  ", None, 7]) == ["A"]

    def test_entries_are_trimmed(self):
        assert playbooks.options([], ["  Spread  "]) == ["Spread"]

    def test_the_result_is_sorted_case_insensitively(self):
        assert playbooks.options(["beta", "Alpha"]) == ["Alpha", "beta"]


class TestSetupRoundTrip:

    def test_a_missing_file_reads_as_nothing_chosen(self, tmp_path):
        setup = playbooks.load_setup(str(tmp_path / "nope.json"))
        assert setup == playbooks.blank_setup()
        assert all(v == "" for v in setup.values())

    def test_unreadable_json_reads_as_nothing_chosen(self, tmp_path):
        path = tmp_path / "setup.json"
        path.write_text("{not json at all")
        assert playbooks.load_setup(str(path)) == playbooks.blank_setup()

    def test_a_json_list_reads_as_nothing_chosen(self, tmp_path):
        # json.load succeeds and returns a list; .get would raise.
        path = tmp_path / "setup.json"
        path.write_text("[1, 2, 3]")
        assert playbooks.load_setup(str(path)) == playbooks.blank_setup()

    def test_what_is_saved_is_what_loads(self, tmp_path):
        path = str(tmp_path / "setup.json")
        chosen = {"off_playbook": "Shotgun Classic", "off_scheme": "Spread",
                  "def_playbook": "Multiple D", "def_scheme": "4-3"}
        ok, _ = playbooks.save_setup(chosen, path)
        assert ok
        assert playbooks.load_setup(path) == chosen

    def test_unknown_keys_are_dropped(self, tmp_path):
        path = str(tmp_path / "setup.json")
        playbooks.save_setup({"off_playbook": "Spread", "junk": "x"}, path)
        assert "junk" not in json.loads(open(path).read())

    def test_values_are_trimmed_on_the_way_in_and_out(self, tmp_path):
        path = str(tmp_path / "setup.json")
        playbooks.save_setup({"off_scheme": "  Air Raid  "}, path)
        assert playbooks.load_setup(path)["off_scheme"] == "Air Raid"

    def test_a_partial_save_leaves_the_rest_blank_not_missing(self, tmp_path):
        path = str(tmp_path / "setup.json")
        playbooks.save_setup({"off_playbook": "Spread"}, path)
        loaded = playbooks.load_setup(path)
        assert set(loaded) == set(playbooks.blank_setup())
        assert loaded["def_playbook"] == ""

    def test_the_directory_is_created_if_absent(self, tmp_path):
        path = str(tmp_path / "fresh" / "setup.json")
        ok, msg = playbooks.save_setup({"off_scheme": "Spread"}, path)
        assert ok, msg
        assert playbooks.load_setup(path)["off_scheme"] == "Spread"

    def test_a_failed_save_leaves_no_temp_file(self, tmp_path, monkeypatch):
        path = str(tmp_path / "setup.json")
        playbooks.save_setup({"off_scheme": "Spread"}, path)
        monkeypatch.setattr(playbooks.os, "replace",
                            lambda *a: (_ for _ in ()).throw(OSError(30, "ro")))
        ok, _ = playbooks.save_setup({"off_scheme": "Pistol"}, path)
        assert not ok
        assert [p.name for p in tmp_path.iterdir()] == ["setup.json"]
        # and the previous choice survived the failure
        assert playbooks.load_setup(path)["off_scheme"] == "Spread"
