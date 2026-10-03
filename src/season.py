"""
Franchise season numbering, defined once.

The game log counted seasons 1, 2, 3... while the Dynasty archive used
calendar years 2020-2040. Three `st.number_input` calls in `app.py` each
declared their own range, so nothing held them together and they drifted:
a franchise could log week 5 of "season 1" and archive the same year as
"season 2027", with no way to line the two up afterwards.

Calendar years won, for two reasons. Nothing was lost by moving the game
log — all 28 shipped rows have a blank Season, and the progression log was
empty — whereas `dynasty_history.json` is gitignored, so any archived
seasons a user already has are calendar years this code cannot see to
migrate. And Madden labels franchise years the same way, so it matches
what is on screen in the game.

Everything that asks for a season imports its bounds from here.
"""

# Wide enough to cover a long franchise in either direction; matches the
# range the Dynasty archive form already used.
SEASON_MIN = 2020
SEASON_MAX = 2040

# Madden NFL 27 ships for the 2026 NFL season, so that is where a fresh
# franchise starts. Only ever a starting point: once anything is logged,
# `game_log.next_season_week` derives the suggestion from the data.
DEFAULT_SEASON = 2026

WEEK_MIN = 1
# 18-game regular season plus playoffs.
WEEK_MAX = 22


def clamp_season(value) -> int:
    """Force a season into the range the form widgets accept.

    A log written before the move to calendar years holds seasons like
    `1`, and `st.number_input` raises outright when handed a value below
    its `min_value`. Clamping keeps a pre-existing file from taking the
    whole tab down; the old row is still readable, it just cannot be the
    default for the next entry.
    """
    try:
        season = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SEASON
    return max(SEASON_MIN, min(SEASON_MAX, season))


def clamp_week(value) -> int:
    """Force a week into the range the form widgets accept."""
    try:
        week = int(value)
    except (TypeError, ValueError):
        return WEEK_MIN
    return max(WEEK_MIN, min(WEEK_MAX, week))
