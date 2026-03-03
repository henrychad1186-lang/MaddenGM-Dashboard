"""
Free Agent & Draft Scout — Browse prospects, compare to current roster.

Provides a demo prospect board (free agents + draft class) along with
helpers to rank targets by position need and projected trade value.
"""

import pandas as pd
from src.trade_engine import get_trade_value

# ──────────────────────────────────────────────
# DEMO PROSPECT DATA
# ──────────────────────────────────────────────

_FREE_AGENTS = [
    # QBs
    {"Name": "D. Prescott",    "Pos": "QB",   "Age": 32, "OVR": 85,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 68, "AWR": 92},
    {"Name": "R. Wilson",      "Pos": "QB",   "Age": 36, "OVR": 78,
     "Dev": "Normal",      "Type": "Free Agent", "SPD": 73, "AWR": 88},
    {"Name": "B. Mayfield",    "Pos": "QB",   "Age": 31, "OVR": 81,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 74, "AWR": 84},
    # HBs
    {"Name": "D. Henry",       "Pos": "HB",   "Age": 31, "OVR": 88,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 88, "AWR": 87},
    {"Name": "A. Jones Sr.",   "Pos": "HB",   "Age": 32, "OVR": 80,
     "Dev": "Normal",      "Type": "Free Agent", "SPD": 92, "AWR": 85},
    {"Name": "T. Pollard",     "Pos": "HB",   "Age": 28, "OVR": 82,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 94, "AWR": 80},
    # WRs
    {"Name": "T. Hill",        "Pos": "WR",   "Age": 32, "OVR": 95,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 99, "AWR": 88},
    {"Name": "D. Adams",       "Pos": "WR",   "Age": 33, "OVR": 87,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 88, "AWR": 93},
    {"Name": "C. Lamb",        "Pos": "WR",   "Age": 27, "OVR": 97,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 93, "AWR": 90},
    # TEs
    {"Name": "T. Kelce",       "Pos": "TE",   "Age": 36, "OVR": 90,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 80, "AWR": 97},
    {"Name": "M. Andrews",     "Pos": "TE",   "Age": 30, "OVR": 89,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 81, "AWR": 91},
    # OL
    {"Name": "T. Smith",       "Pos": "LT",   "Age": 29, "OVR": 88,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 72, "AWR": 85},
    {"Name": "R. Armstead",    "Pos": "LT",   "Age": 33, "OVR": 83,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 68, "AWR": 88},
    # EDGE
    {"Name": "M. Garrett",     "Pos": "EDGE", "Age": 29, "OVR": 97,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 87, "AWR": 88},
    {"Name": "B. Burns",       "Pos": "EDGE", "Age": 27, "OVR": 89,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 88, "AWR": 83},
    {"Name": "H. Anderson",    "Pos": "EDGE", "Age": 30, "OVR": 84,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 84, "AWR": 81},
    # DT
    {"Name": "D. Lawrence",    "Pos": "DT",   "Age": 32, "OVR": 88,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 78, "AWR": 86},
    {"Name": "Q. Williams",    "Pos": "DT",   "Age": 29, "OVR": 85,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 76, "AWR": 82},
    # LBs
    {"Name": "F. Warner",      "Pos": "MLB",  "Age": 29, "OVR": 90,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 88, "AWR": 91},
    {"Name": "D. White",       "Pos": "MLB",  "Age": 32, "OVR": 82,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 84, "AWR": 90},
    # CBs
    {"Name": "J. Ramsey",      "Pos": "CB",   "Age": 31, "OVR": 88,
     "Dev": "Superstar X", "Type": "Free Agent", "SPD": 91, "AWR": 92},
    {"Name": "D. Samuel",      "Pos": "CB",   "Age": 27, "OVR": 84,
     "Dev": "Star",        "Type": "Free Agent", "SPD": 93, "AWR": 82},
    # Safeties
    {"Name": "K. Fitzpatrick", "Pos": "FS",   "Age": 29, "OVR": 88,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 92, "AWR": 90},
    {"Name": "J. Simmons",     "Pos": "SS",   "Age": 29, "OVR": 87,
     "Dev": "Superstar",   "Type": "Free Agent", "SPD": 90, "AWR": 89},
]

_DRAFT_CLASS = [
    {"Name": "D. McKinney (R)",   "Pos": "QB",   "Age": 22, "OVR": 75,
     "Dev": "Superstar X", "Type": "Draft Prospect", "SPD": 82, "AWR": 74},
    {"Name": "C. Thompson (R)",   "Pos": "QB",   "Age": 21, "OVR": 72,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 86, "AWR": 68},
    {"Name": "T. Jackson (R)",    "Pos": "HB",   "Age": 21, "OVR": 78,
     "Dev": "Superstar X", "Type": "Draft Prospect", "SPD": 97, "AWR": 72},
    {"Name": "M. Harrison Jr. (R)", "Pos": "WR", "Age": 22, "OVR": 79,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 91, "AWR": 76},
    {"Name": "J. Egbuka (R)",     "Pos": "WR",   "Age": 22, "OVR": 77,
     "Dev": "Star",        "Type": "Draft Prospect", "SPD": 90, "AWR": 78},
    {"Name": "T. McMillan (R)",   "Pos": "WR",   "Age": 21, "OVR": 76,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 96, "AWR": 70},
    {"Name": "K. Fentress (R)",   "Pos": "TE",   "Age": 22, "OVR": 74,
     "Dev": "Star",        "Type": "Draft Prospect", "SPD": 84, "AWR": 71},
    {"Name": "A. Fontenot (R)",   "Pos": "LT",   "Age": 22, "OVR": 76,
     "Dev": "Star",        "Type": "Draft Prospect", "SPD": 68, "AWR": 72},
    {"Name": "R. Nelson Jr. (R)", "Pos": "EDGE", "Age": 22, "OVR": 80,
     "Dev": "Superstar X", "Type": "Draft Prospect", "SPD": 85, "AWR": 75},
    {"Name": "M. Bowen (R)",      "Pos": "EDGE", "Age": 21, "OVR": 77,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 86, "AWR": 72},
    {"Name": "T. Walker IV (R)",  "Pos": "DT",   "Age": 22, "OVR": 76,
     "Dev": "Star",        "Type": "Draft Prospect", "SPD": 78, "AWR": 73},
    {"Name": "L. Graham (R)",     "Pos": "MLB",  "Age": 22, "OVR": 77,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 87, "AWR": 74},
    {"Name": "W. Rankins (R)",    "Pos": "CB",   "Age": 21, "OVR": 78,
     "Dev": "Superstar X", "Type": "Draft Prospect", "SPD": 94, "AWR": 73},
    {"Name": "M. Ford (R)",       "Pos": "CB",   "Age": 22, "OVR": 75,
     "Dev": "Star",        "Type": "Draft Prospect", "SPD": 92, "AWR": 70},
    {"Name": "T. Campbell (R)",   "Pos": "FS",   "Age": 22, "OVR": 76,
     "Dev": "Superstar",   "Type": "Draft Prospect", "SPD": 91, "AWR": 73},
]


def get_prospects(pos_filter: str = "All", type_filter: str = "All") -> pd.DataFrame:
    """Return prospects filtered by position and type.

    Args:
        pos_filter: Position abbreviation or 'All'.
        type_filter: 'Free Agent', 'Draft Prospect', or 'All'.

    Returns:
        DataFrame with prospect data sorted by OVR descending.
    """
    all_prospects = _FREE_AGENTS + _DRAFT_CLASS
    df = pd.DataFrame(all_prospects)

    if type_filter != "All":
        df = df[df["Type"] == type_filter]
    if pos_filter != "All":
        df = df[df["Pos"] == pos_filter]

    # Compute trade value for each prospect
    df = df.copy()
    df["Trade_Value"] = df.apply(lambda r: get_trade_value(r.to_dict()), axis=1)

    return df.sort_values("OVR", ascending=False).reset_index(drop=True)


def get_position_needs(team: str) -> list[dict]:
    """Identify the team's weakest positions and recommend targets.

    Compares each team position's average OVR against the prospect pool to
    surface the highest-impact additions.

    Returns:
        List of dicts: {pos, team_avg_ovr, best_prospect_name,
                        best_prospect_ovr, upgrade, priority}.
    """
    from src.roster import get_position_grades

    grades = get_position_grades(team)
    if not grades:
        return []

    prospects_df = get_prospects()
    needs = []

    for g in grades:
        pos = g["pos"]
        team_avg = g["avg_ovr"]
        pos_prospects = prospects_df[prospects_df["Pos"] == pos]
        if pos_prospects.empty:
            continue
        best = pos_prospects.iloc[0]
        upgrade = round(float(best["OVR"]) - team_avg, 1)
        if upgrade <= 0:
            priority = "Set"
        elif upgrade < 5:
            priority = "Monitor"
        elif upgrade < 10:
            priority = "Need"
        else:
            priority = "Urgent"

        needs.append({
            "pos": pos,
            "team_avg_ovr": team_avg,
            "grade": g["grade"],
            "best_prospect_name": best["Name"],
            "best_prospect_ovr": int(best["OVR"]),
            "best_prospect_type": best["Type"],
            "upgrade": upgrade,
            "priority": priority,
        })

    # Sort: Urgent first, then Need, Monitor, Set
    _priority_order = {"Urgent": 0, "Need": 1, "Monitor": 2, "Set": 3}
    needs.sort(key=lambda x: (_priority_order.get(x["priority"], 4), -x["upgrade"]))
    return needs


def get_prospect_positions() -> list[str]:
    """Return sorted list of unique positions across all prospects."""
    all_pos = sorted({p["Pos"] for p in _FREE_AGENTS + _DRAFT_CLASS})
    return ["All"] + all_pos
