"""
Dynasty Tracker — Season archival, era tracking, and career leaderboards.
"""

import json
import os
import pandas as pd

# Path for persisted history file (sits next to the app)
_HISTORY_FILE = os.path.join(os.path.dirname(
    os.path.dirname(__file__)), "dynasty_history.json")

# ──────────────────────────────────────────────
# DEMO HISTORY DATA (3 mock seasons)
# ──────────────────────────────────────────────

DEMO_HISTORY = [
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
    """Load dynasty history from file, falling back to demo data."""
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return DEMO_HISTORY.copy()


def archive_season(season_data: dict, existing_history: list[dict] | None = None) -> list[dict]:
    """
    Add a new season to the dynasty history and persist to disk.
    Returns the updated history list.
    """
    history = existing_history if existing_history is not None else load_history()

    # Prevent duplicate season numbers
    if any(s["season"] == season_data.get("season") for s in history):
        # Update in place
        history = [s if s["season"] != season_data["season"]
                   else season_data for s in history]
    else:
        history.append(season_data)

    # Sort by season
    history.sort(key=lambda s: s["season"])

    # Persist
    try:
        with open(_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass  # If write fails, data is still in memory

    return history


def get_career_leaders(history: list[dict]) -> pd.DataFrame:
    """
    Aggregate stats across seasons to build a career leaderboard.
    Returns a DataFrame with player name, category, and total.
    """
    leaders = {}

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

    df = pd.DataFrame(leaders.values())
    df["Total Yds"] = df["Rush Yds"] + df["Rec Yds"]
    df = df.sort_values("Total Yds", ascending=False).reset_index(drop=True)
    return df


def get_eras(history: list[dict]) -> list[str]:
    """Return unique era names from history."""
    return list(dict.fromkeys(s.get("era", "Unknown") for s in history))
