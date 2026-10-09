"""
Dynasty Tracker — Season archival, era tracking, and career leaderboards.
"""

import json
import os
from typing import Optional

import pandas as pd

# Path for persisted history file (sits next to the app)
_HISTORY_FILE = os.path.join(os.path.dirname(
    os.path.dirname(__file__)), "dynasty_history.json")

# ──────────────────────────────────────────────
# SAMPLE HISTORY — never returned as the user's own
# ──────────────────────────────────────────────
# `load_history` used to fall back to this whenever no history file
# existed, so a new franchise opened the Dynasty tab to three seasons it
# had not played: a 2025 Super Bowl win, Jordan Love as MVP, a career
# leaderboard built from all of it. Presented in exactly the styling
# real archived seasons use, with nothing marking it as a sample.
#
# Kept as an illustration of the shape `archive_season` expects. Nothing
# in the app reads it.

SAMPLE_HISTORY = [
    {
        "season": 2024,
        "era": "The Jordan Love Era",
        "record": "12-5",
        "wins": 12,
        "losses": 5,
        "playoff_result": "NFC Championship",
        "mvp": "Jordan Love",
        "mvp_stats": "4,200 Yds / 34 TD / 8 INT",
        "top_rusher": "Josh Jacobs",
        "rush_yards": 1150,
        "top_receiver": "Jayden Reed",
        "rec_yards": 1320,
        "notes": "Breakout season for Love — first playoff run as the starter.",
    },
    {
        "season": 2025,
        "era": "The Jordan Love Era",
        "record": "14-3",
        "wins": 14,
        "losses": 3,
        "playoff_result": "Super Bowl Champions 🏆",
        "mvp": "Jordan Love",
        "mvp_stats": "4,600 Yds / 38 TD / 6 INT",
        "top_rusher": "Josh Jacobs",
        "rush_yards": 1280,
        "top_receiver": "Jayden Reed",
        "rec_yards": 1510,
        "notes": "Dynasty cemented — dominant run through playoffs.",
    },
    {
        "season": 2026,
        "era": "Defending Champs",
        "record": "10-7",
        "wins": 10,
        "losses": 7,
        "playoff_result": "Wild Card Round",
        "mvp": "Tucker Kraft",
        "mvp_stats": "980 Yds / 12 TD",
        "top_rusher": "Josh Jacobs",
        "rush_yards": 920,
        "top_receiver": "Tucker Kraft",
        "rec_yards": 980,
        "notes": "Injury-plagued season — early playoff exit.",
    },
]


# ──────────────────────────────────────────────
# CORE FUNCTIONS
# ──────────────────────────────────────────────

def load_history() -> list[dict]:
    """Load dynasty history from file.

    Returns an empty list when there is nothing archived yet. It must not
    fall back to `SAMPLE_HISTORY`: a franchise with no seasons on record
    has no history, and inventing one puts three seasons the user never
    played into their timeline, their chronicles and their career
    leaderboard.
    """
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, "r") as f:
            loaded = json.load(f)
    except Exception:
        return []
    # A file holding anything but a list of seasons is not history.
    return loaded if isinstance(loaded, list) else []


def _season_key(entry) -> "float | None":
    """An entry's season as a number, or None if it has no usable one.

    Hand edits produce "2027" and 2027.0 as readily as 2027; all three
    are the same season.
    """
    if not isinstance(entry, dict):
        return None
    try:
        return float(entry.get("season"))
    except (TypeError, ValueError):
        return None


def save_history(history: list) -> bool:
    """Write the history atomically. Returns False if it couldn't.

    Atomic because a crash mid-write used to leave truncated JSON, which
    load_history reads as "no history" — every archived season gone.
    """
    tmp = f"{_HISTORY_FILE}.tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(history, f, indent=2)
        os.replace(tmp, _HISTORY_FILE)
        return True
    except Exception:
        return False


def archive_and_save(season_data: dict,
                     existing_history: Optional[list] = None) -> "tuple[list, bool]":
    """Add (or replace) a season and persist. Returns (history, saved).

    Every entry already in the file is kept. An earlier version dropped
    any entry whose season wasn't a Python int and then wrote the file
    back, so a hand-edited "2027" or 2027.0 was deleted for good the next
    time any season was archived. Entries with no usable season now stay
    in place, after the numbered ones.
    """
    history = list(existing_history if existing_history is not None
                   else load_history())
    target = _season_key(season_data)

    if target is not None and any(_season_key(s) == target for s in history):
        history = [season_data if _season_key(s) == target else s
                   for s in history]
    else:
        history.append(season_data)

    # Numbered seasons in order, then anything without one, as found.
    numbered = sorted((s for s in history if _season_key(s) is not None),
                      key=_season_key)
    history = numbered + [s for s in history if _season_key(s) is None]
    return history, save_history(history)


def archive_season(
    season_data: dict, existing_history: Optional[list[dict]] = None
) -> list[dict]:
    """
    Add a new season to the dynasty history and persist to disk.
    Returns the updated history list (see archive_and_save for whether
    the write succeeded).
    """
    return archive_and_save(season_data, existing_history)[0]


def get_career_leaders(history: list[dict]) -> pd.DataFrame:
    """
    Aggregate stats across seasons to build a career leaderboard.
    Returns a DataFrame with player name, category, and total.
    """
    leaders = {}

    # Without this an empty history raises KeyError on "Rush Yds" below —
    # which is what a franchise with nothing archived now has, since
    # `load_history` stopped substituting the sample seasons.
    if not history:
        return pd.DataFrame(
            columns=["Player", "Rush Yds", "Rec Yds", "Seasons", "Total Yds"])

    for season in history:
        # Rushing
        rusher = season.get("top_rusher", "Unknown")
        rush_yds = season.get("rush_yards", 0)
        if rusher not in leaders:
            leaders[rusher] = {"Player": rusher,
                               "Rush Yds": 0, "Rec Yds": 0, "Seasons": 0}
        leaders[rusher]["Rush Yds"] += rush_yds
        leaders[rusher]["Seasons"] += 1

        # Receiving
        receiver = season.get("top_receiver", "Unknown")
        rec_yds = season.get("rec_yards", 0)
        if receiver not in leaders:
            leaders[receiver] = {"Player": receiver,
                                 "Rush Yds": 0, "Rec Yds": 0, "Seasons": 0}
        leaders[receiver]["Rec Yds"] += rec_yds
        if receiver != rusher:
            leaders[receiver]["Seasons"] += 1

    if not leaders:
        return pd.DataFrame(
            columns=["Player", "Rush Yds", "Rec Yds", "Seasons", "Total Yds"]
        )

    df = pd.DataFrame(leaders.values())
    df["Total Yds"] = df["Rush Yds"] + df["Rec Yds"]
    df = df.sort_values("Total Yds", ascending=False).reset_index(drop=True)
    return df


def get_eras(history: list[dict]) -> list[str]:
    """Return unique era names from history."""
    return list(dict.fromkeys(s.get("era", "Unknown") for s in history))
