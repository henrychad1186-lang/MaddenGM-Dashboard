"""
Roster Explorer — Browse team rosters with position-group filtering.
Loads real roster data from data/packers_roster.csv when available.
"""

import os
import pandas as pd

# ──────────────────────────────────────────────
# POSITION → GROUP MAPPING
# ──────────────────────────────────────────────

_OFFENSE_POS = {"QB", "HB", "FB", "WR",
                "TE", "LT", "LG", "C", "RG", "RT", "OL"}
_DEFENSE_POS = {"EDGE", "REDG", "LEDG", "DT", "DL", "MLB", "OLB", "LOLB", "ROLB",
                "CB", "FS", "SS", "S", "LB"}
_ST_POS = {"K", "P"}


def _assign_group(pos: str) -> str:
    pos_upper = pos.upper().strip()
    if pos_upper in _OFFENSE_POS:
        return "Offense"
    elif pos_upper in _DEFENSE_POS:
        return "Defense"
    elif pos_upper in _ST_POS:
        return "Special Teams"
    return "Offense"  # default


def _normalize_pos(pos: str) -> str:
    """Normalize position names (e.g., REDG/LEDG → EDGE)."""
    pos_upper = pos.upper().strip()
    if pos_upper in ("REDG", "LEDG"):
        return "EDGE"
    return pos_upper


# ──────────────────────────────────────────────
# LOAD DATA — CSV first, fallback to demo
# ──────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_ROSTER_CSV = os.path.join(_DATA_DIR, "packers_roster.csv")


def _load_rosters() -> pd.DataFrame:
    """Load roster data from CSV if available, otherwise use minimal demo."""
    if os.path.exists(_ROSTER_CSV):
        df = pd.read_csv(_ROSTER_CSV)
        # Ensure required columns
        if "Team" not in df.columns:
            df["Team"] = "GB"
        if "Dev" not in df.columns:
            df["Dev"] = "Normal"
        # Normalize positions and assign groups
        df["Pos"] = df["Pos"].apply(_normalize_pos)
        df["Group"] = df["Pos"].apply(_assign_group)
        return df
    else:
        # Minimal fallback demo
        return pd.DataFrame([
            {"Team": "GB", "Name": "Demo Player", "Pos": "QB", "OVR": 75,
             "Age": 25, "Dev": "Normal", "Group": "Offense"},
        ])


ALL_ROSTERS = _load_rosters()

TEAMS = sorted(ALL_ROSTERS["Team"].unique().tolist())
POSITION_GROUPS = ["All", "Offense", "Defense", "Special Teams"]


# ──────────────────────────────────────────────
# CORE FUNCTIONS
# ──────────────────────────────────────────────

def get_roster(team: str, group: str = "All") -> pd.DataFrame:
    """Return the roster DataFrame for a team, optionally filtered by group."""
    df = ALL_ROSTERS[ALL_ROSTERS["Team"] == team].copy()
    if group and group != "All":
        df = df[df["Group"] == group]
    return df.reset_index(drop=True)


def get_team_summary(team: str) -> dict:
    """Return summary stats for a team's roster."""
    df = ALL_ROSTERS[ALL_ROSTERS["Team"] == team]
    if df.empty:
        return {"count": 0, "avg_ovr": 0, "avg_age": 0, "best_player": "N/A"}
    return {
        "count": len(df),
        "avg_ovr": round(df["OVR"].mean(), 1),
        "avg_age": round(df["Age"].mean(), 1),
        "best_player": df.loc[df["OVR"].idxmax(), "Name"],
        "best_ovr": int(df["OVR"].max()),
    }


def ovr_color(ovr: int) -> str:
    """Return a CSS color string based on OVR rating tier."""
    if ovr >= 90:
        return "#00e676"   # Elite — green
    elif ovr >= 80:
        return "#2196f3"   # Great — blue
    elif ovr >= 70:
        return "#ffc107"   # Average — amber
    else:
        return "#ff5252"   # Below average — red


def ovr_label(ovr: int) -> str:
    """Return a tier label based on OVR."""
    if ovr >= 90:
        return "Elite"
    elif ovr >= 80:
        return "Great"
    elif ovr >= 70:
        return "Average"
    else:
        return "Developing"


def _letter_grade(avg_ovr: float) -> str:
    """Convert an average OVR to a letter grade."""
    if avg_ovr >= 90:
        return "A+"
    elif avg_ovr >= 85:
        return "A"
    elif avg_ovr >= 80:
        return "B+"
    elif avg_ovr >= 75:
        return "B"
    elif avg_ovr >= 70:
        return "C"
    else:
        return "D"


def _grade_color(grade: str) -> str:
    """Return a CSS color for a letter grade."""
    return {
        "A+": "#00e676", "A": "#66bb6a", "B+": "#2196f3",
        "B": "#42a5f5", "C": "#ffc107", "D": "#ff5252",
    }.get(grade, "#ffffff")


# Position display order for depth chart / grading
_POS_ORDER = ["QB", "HB", "WR", "TE", "LT", "LG", "C", "RG", "RT",
              "EDGE", "DT", "MLB", "OLB", "CB", "SS", "FS"]


def get_position_grades(team: str) -> list[dict]:
    """Return letter grades per position group for a team.

    Returns list of dicts: {pos, count, avg_ovr, grade, color}.
    """
    df = ALL_ROSTERS[ALL_ROSTERS["Team"] == team]
    if df.empty:
        return []
    grades = []
    for pos in _POS_ORDER:
        pos_df = df[df["Pos"] == pos]
        if pos_df.empty:
            continue
        avg = round(pos_df["OVR"].mean(), 1)
        grade = _letter_grade(avg)
        grades.append({
            "pos": pos,
            "count": len(pos_df),
            "avg_ovr": avg,
            "grade": grade,
            "color": _grade_color(grade),
        })
    return grades


def _parse_sal(val) -> float:
    """Parse salary string like '$3M', '$1.29M', '$600K' to float millions."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    s = str(val).strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0
    try:
        if s.upper().endswith("M"):
            return float(s[:-1])
        elif s.upper().endswith("K"):
            return float(s[:-1]) / 1000.0
        return float(s)
    except ValueError:
        return 0.0


def get_cap_summary(team: str) -> dict:
    """Return cap summary for a team.

    Returns dict with total_savings, total_penalty, and a list of
    per-player dicts sorted by penalty descending.
    """
    df = ALL_ROSTERS[ALL_ROSTERS["Team"] == team].copy()
    if df.empty or "Savings" not in df.columns:
        return {"total_savings": 0, "total_penalty": 0, "players": []}

    players = []
    total_sav = 0.0
    total_pen = 0.0
    for _, row in df.iterrows():
        sav = _parse_sal(row.get("Savings"))
        pen = _parse_sal(row.get("Penalty"))
        total_sav += sav
        total_pen += pen
        players.append({
            "Name": row["Name"], "Pos": row["Pos"], "OVR": int(row["OVR"]),
            "Savings": sav, "Penalty": pen,
        })
    players.sort(key=lambda x: x["Penalty"], reverse=True)
    return {
        "total_savings": round(total_sav, 2),
        "total_penalty": round(total_pen, 2),
        "players": players,
    }
