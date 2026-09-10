"""
Tests for the append-only game log writer.

The failure this guards against is the one `roster_csv` already shipped
once: a writer that rebuilds the file from its own normalised view and
silently rewrites rows the user never touched.
"""

import pandas as pd
import pytest

from src import game_log


def _entry(**overrides):
    entry = {
        "Season": 1, "Week": 5, "Opponent": "CHI",
        "Points_For": 27, "Points_Against": 20,
        "Pass_Yards": 250, "Rush_Yards": 120, "First_Downs": 22,
        "Turnovers": 1, "TOP": "31:12", "RZ_TD_Made": 3,
        "Pass_Yards_Allowed": 190, "Rush_Yards_Allowed": 95,
        "Sacks_For": 2, "Takeaways": 2, "Playbook": "WestCoast Zone Run",
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def log_file(tmp_path):
    """A two-row log in the shipped schema, second row legacy (blank week)."""
    path = tmp_path / "game_logs.csv"
    path.write_text(
        "GAME_ID,Season,Week,Team,Opponent,Result,Points_For,Points_Against,"
        "Pass_Yards,Rush_Yards,Total_Yards,First_Downs,Turnovers,TOP,"
        "RZ_TD_Made,Pass_Yards_Allowed,Rush_Yards_Allowed,"
        "Total_Yards_Allowed,Sacks_For,Takeaways,Point_Differential,Playbook\n"
        "1,,,GB,IND,W,35,10,241,160,401,25,1,14:01,2,175,100,275,3,1,25,"
        "WestCoast Zone Run\n"
    )
    return str(path)


class TestDeriveFields:

    def test_totals_are_summed_not_retyped(self):
        out = game_log.derive_fields(_entry())
        assert out["Total_Yards"] == 370
        assert out["Total_Yards_Allowed"] == 285

    def test_point_differential_follows_the_score(self):
        assert game_log.derive_fields(_entry())["Point_Differential"] == 7

    def test_win_loss_follow_the_score(self):
        assert game_log.derive_fields(_entry())["Result"] == "W"
        assert game_log.derive_fields(
            _entry(Points_For=10, Points_Against=24))["Result"] == "L"

    def test_a_tie_is_not_recorded_as_a_loss(self):
        # 20-20 is a real NFL outcome; "L" would record a game that did
        # not happen that way.
        out = game_log.derive_fields(_entry(Points_For=20, Points_Against=20))
        assert out["Result"] == "T"
        assert out["Point_Differential"] == 0

    def test_blank_yardage_counts_as_zero_for_the_total(self):
        out = game_log.derive_fields(_entry(Rush_Yards=""))
        assert out["Total_Yards"] == 250

    def test_does_not_mutate_the_caller_dict(self):
        entry = _entry()
        game_log.derive_fields(entry)
        assert "Result" not in entry


class TestNextGameId:

    def test_one_past_the_highest(self, log_file):
        assert game_log.next_game_id(pd.read_csv(log_file)) == 2

    def test_empty_log_starts_at_one(self):
        assert game_log.next_game_id(pd.DataFrame()) == 1

    def test_ignores_non_numeric_ids(self):
        df = pd.DataFrame({"GAME_ID": ["x", 4, None]})
        assert game_log.next_game_id(df) == 5

    def test_uses_the_max_not_the_row_count(self):
        # Deleting a middle row must not hand the next game a used id.
        df = pd.DataFrame({"GAME_ID": [1, 9]})
        assert game_log.next_game_id(df) == 10


class TestReadLog:

    def test_missing_file_is_empty_not_an_error(self, tmp_path):
        assert game_log.read_log(str(tmp_path / "nope.csv")).empty

    def test_unreadable_file_is_empty_not_an_error(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("")
        assert game_log.read_log(str(path)).empty


class TestAppendGame:

    def test_existing_rows_are_left_byte_identical(self, log_file):
        before = open(log_file).read().strip()
        ok, _ = game_log.append_game(log_file, _entry(), "GB")
        assert ok
        after = open(log_file).read()
        assert after.startswith(before)

    def test_columns_are_unchanged(self, log_file):
        before = list(pd.read_csv(log_file).columns)
        game_log.append_game(log_file, _entry(), "GB")
        assert list(pd.read_csv(log_file).columns) == before

    def test_the_new_row_carries_week_and_season(self, log_file):
        game_log.append_game(log_file, _entry(Season=2, Week=11), "GB")
        row = pd.read_csv(log_file).iloc[-1]
        assert row["Season"] == 2 and row["Week"] == 11

    def test_legacy_blank_week_stays_blank(self, log_file):
        game_log.append_game(log_file, _entry(), "GB")
        out = pd.read_csv(log_file)
        assert pd.isna(out.iloc[0]["Week"])

    def test_derived_columns_land_in_the_file(self, log_file):
        game_log.append_game(log_file, _entry(), "GB")
        row = pd.read_csv(log_file).iloc[-1]
        assert row["Total_Yards"] == 370
        assert row["Point_Differential"] == 7
        assert row["Result"] == "W"

    def test_writing_to_a_missing_file_creates_a_usable_log(self, tmp_path):
        path = str(tmp_path / "new.csv")
        ok, _ = game_log.append_game(path, _entry(), "GB")
        assert ok
        out = pd.read_csv(path)
        assert len(out) == 1
        assert out.iloc[0]["GAME_ID"] == 1
        assert out.iloc[0]["Team"] == "GB"
        assert out.iloc[0]["Opponent"] == "CHI"

    def test_two_appends_do_not_reuse_an_id(self, log_file):
        game_log.append_game(log_file, _entry(), "GB")
        game_log.append_game(log_file, _entry(Week=6), "GB")
        ids = pd.read_csv(log_file)["GAME_ID"].tolist()
        assert ids == [1, 2, 3]

    def test_read_only_filesystem_reports_instead_of_raising(
            self, log_file, monkeypatch):
        # chmod is not usable here: the suite runs as root, which bypasses
        # the permission bit. Fail the write itself instead. Reads must
        # still work, or this would prove nothing about the write path.
        import builtins
        real_open = builtins.open

        def _open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in ("w", "a", "+")):
                raise OSError("read-only file system")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _open)
        ok, message = game_log.append_game(log_file, _entry(), "GB")
        assert ok is False
        assert "read-only" in message

    def test_a_failed_write_leaves_the_log_untouched(
            self, log_file, monkeypatch):
        before = open(log_file, "rb").read()
        import builtins
        real_open = builtins.open

        def _open(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in ("w", "a", "+")):
                raise OSError("read-only file system")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _open)
        game_log.append_game(log_file, _entry(), "GB")
        monkeypatch.undo()
        assert open(log_file, "rb").read() == before

    def test_a_truncated_log_gets_a_header_not_a_bare_row(self, tmp_path):
        # An existing but empty file used to take a headerless append:
        # pandas then read the game itself as the header row and the file
        # came back with zero rows, while the form reported success.
        path = str(tmp_path / "empty.csv")
        open(path, "w").close()
        ok, _ = game_log.append_game(path, _entry(), "GB")
        assert ok
        out = pd.read_csv(path)
        assert len(out) == 1
        assert "GAME_ID" in out.columns
        assert out.iloc[0]["Opponent"] == "CHI"

    def test_a_whitespace_only_log_is_treated_as_empty(self, tmp_path):
        path = str(tmp_path / "blank.csv")
        open(path, "w").write("\n\n  \n")
        ok, _ = game_log.append_game(path, _entry(), "GB")
        assert ok
        assert len(pd.read_csv(path)) == 1

    def test_an_unreadable_log_with_content_is_not_overwritten(self, tmp_path):
        # Starting fresh here would destroy whatever the user has.
        path = tmp_path / "garbage.csv"
        path.write_bytes(b"\x00\x01 not a csv at all\n\x02")
        before = path.read_bytes()
        ok, message = game_log.append_game(str(path), _entry(), "GB")
        assert ok is False
        assert "could not be read" in message
        assert path.read_bytes() == before

    def test_a_log_without_a_game_id_column_still_works(self, tmp_path):
        # The success message used to read the id back out of the new
        # row, which a user-made log need not have a column for.
        path = tmp_path / "own.csv"
        path.write_text("Team,Opponent,Points_For,Points_Against\n"
                        "GB,IND,35,10\n")
        ok, message = game_log.append_game(str(path), _entry(), "GB")
        assert ok, message
        out = pd.read_csv(path)
        assert len(out) == 2
        assert out.iloc[-1]["Opponent"] == "CHI"

    def test_a_field_the_file_does_not_have_is_dropped(self, log_file):
        game_log.append_game(log_file, _entry(Nonsense="x"), "GB")
        assert "Nonsense" not in pd.read_csv(log_file).columns


class TestParseTop:

    def test_reads_minutes_and_seconds(self):
        assert game_log.parse_top("31:12") == pytest.approx(31.2)

    @pytest.mark.parametrize("bad", ["", "31", "abc", "31:xx", "31:75", None,
                                     "-1:30"])
    def test_rejects_what_the_chart_would_silently_drop(self, bad):
        assert game_log.parse_top(bad) is None

    def test_accepts_a_plain_number(self):
        assert game_log.parse_top(30) == 30.0


class TestDuplicateWeek:

    def test_flags_a_week_already_logged(self, log_file):
        df = pd.read_csv(log_file)
        df.loc[len(df)] = df.iloc[0]
        df.loc[len(df) - 1, ["Season", "Week"]] = [1, 5]
        assert game_log.duplicate_week(df, 1, 5, "GB") is True

    def test_allows_a_new_week(self, log_file):
        df = pd.read_csv(log_file)
        assert game_log.duplicate_week(df, 1, 5, "GB") is False

    def test_blank_legacy_rows_never_collide(self):
        # All 28 shipped games have blank Season/Week; treating blank as a
        # match would make every one of them a duplicate of the others.
        df = pd.read_csv("data/game_logs.csv")
        assert game_log.duplicate_week(df, 1, 1, "GB") is False

    def test_another_team_is_not_a_duplicate(self, log_file):
        df = pd.read_csv(log_file)
        df.loc[len(df)] = df.iloc[0]
        df.loc[len(df) - 1, ["Season", "Week", "Team"]] = [1, 5, "CHI"]
        assert game_log.duplicate_week(df, 1, 5, "GB") is False

    def test_empty_log_has_no_duplicates(self):
        assert game_log.duplicate_week(pd.DataFrame(), 1, 1, "GB") is False


class TestNextSeasonWeek:

    def test_all_blank_log_starts_at_one_one(self):
        df = pd.read_csv("data/game_logs.csv")
        assert game_log.next_season_week(df, "GB") == (1, 1)

    def test_advances_past_the_last_logged_week(self, log_file):
        df = pd.read_csv(log_file)
        df.loc[len(df)] = df.iloc[0]
        df.loc[len(df) - 1, ["Season", "Week"]] = [2, 7]
        assert game_log.next_season_week(df, "GB") == (2, 8)

    def test_empty_log_starts_at_one_one(self):
        assert game_log.next_season_week(pd.DataFrame(), "GB") == (1, 1)


class TestAgainstTheShippedLog:
    """The clean two-row fixture above is not enough.

    The real log has a game missing four stats, which forces those
    columns to float on read. Every test in `TestAppendGame` passed
    while `to_csv` was rewriting each untouched `25` as `25.0` and each
    `Week` as `5.0`, because the fixture had no gaps to promote. These
    run against a copy of the file the app actually ships.
    """

    @pytest.fixture
    def real_log_copy(self, tmp_path):
        path = tmp_path / "game_logs.csv"
        path.write_bytes(open("data/game_logs.csv", "rb").read())
        return str(path)

    def test_appending_leaves_the_file_above_byte_identical(
            self, real_log_copy):
        before = open(real_log_copy, "rb").read()
        ok, _ = game_log.append_game(real_log_copy, _entry(), "GB")
        assert ok
        assert open(real_log_copy, "rb").read().startswith(before)

    def test_integers_are_not_rendered_as_floats(self, real_log_copy):
        game_log.append_game(real_log_copy, _entry(Season=2, Week=11), "GB")
        last = open(real_log_copy).read().strip().splitlines()[-1]
        assert ".0" not in last, last
        cells = last.split(",")
        assert cells[1] == "2" and cells[2] == "11"

    def test_the_appended_row_reads_back_correctly(self, real_log_copy):
        game_log.append_game(real_log_copy, _entry(), "GB")
        out = pd.read_csv(real_log_copy)
        row = out.iloc[-1]
        assert row["Opponent"] == "CHI"
        assert row["Total_Yards"] == 370
        assert row["Result"] == "W"
        assert len(out) == 29

    def test_a_comma_in_a_field_does_not_shift_the_columns(
            self, real_log_copy):
        game_log.append_game(
            real_log_copy, _entry(Playbook="Spread, Air Raid"), "GB")
        out = pd.read_csv(real_log_copy)
        assert out.iloc[-1]["Playbook"] == "Spread, Air Raid"
        assert out.iloc[-1]["Opponent"] == "CHI"

    def test_a_file_with_no_trailing_newline_does_not_join_rows(
            self, real_log_copy):
        raw = open(real_log_copy).read().rstrip("\n")
        open(real_log_copy, "w").write(raw)
        game_log.append_game(real_log_copy, _entry(), "GB")
        assert len(pd.read_csv(real_log_copy)) == 29

    def test_every_entry_field_exists_in_the_real_file(self):
        # If the shipped log loses a column the form writes to, the value
        # is silently dropped by row_to_log_schema.
        df = pd.read_csv("data/game_logs.csv")
        missing = [f for f in game_log.ENTRY_FIELDS if f not in df.columns]
        assert not missing, f"form writes columns the log lacks: {missing}"

    def test_the_shipped_log_carries_season_and_week(self):
        df = pd.read_csv("data/game_logs.csv")
        assert "Season" in df.columns and "Week" in df.columns
