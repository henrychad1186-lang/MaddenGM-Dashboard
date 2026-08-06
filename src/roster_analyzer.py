"""
Cut or Keep Analyzer — evaluate each player's roster status.

Combines trade value, cap savings/penalties, positional depth, age,
and OVR to recommend: KEEP / TRADE / CUT for every player.
"""

from collections import defaultdict

import pandas as pd
from src.roster import get_roster, get_cap_summary
from src.trade_engine import get_trade_value


def analyze_roster(team: str, extra_players: "list[dict] | None" = None) -> list[dict]:
    """Return a list of player analysis dicts with verdicts.

    Each dict contains:
        Name, Pos, OVR, Age, Dev, Trade_Value, Savings, Penalty,
        Depth, Verdict, Verdict_Reason
    """
    roster = get_roster(team, "All", extra_players)
    cap = get_cap_summary(team, extra_players)

    # cap["players"] is sorted by Penalty and can't be zipped positionally
    # against `roster`. A plain {Name: entry} dict would let same-named
    # players (AI GM explicitly allows duplicate names) silently overwrite
    # each other's cap lookup. Instead keep a per-name queue and consume
    # the best Pos+OVR match for each roster row, so duplicates each get
    # paired with their own cap entry instead of all sharing the last one.
    cap_by_name = defaultdict(list)
    for p in cap["players"]:
        cap_by_name[p["Name"]].append(p)

    results = []
    for _, row in roster.iterrows():
        player = row.to_dict()
        tv = get_trade_value(player)

        candidates = cap_by_name.get(row["Name"], [])
        if candidates:
            match_idx = next(
                (i for i, c in enumerate(candidates)
                 if c["Pos"] == row["Pos"] and c["OVR"] == int(row["OVR"])),
                0,
            )
            cap_info = candidates.pop(match_idx)
        else:
            cap_info = {"Savings": 0, "Penalty": 0}
        savings = cap_info["Savings"]
        penalty = cap_info["Penalty"]

        # Count positional depth (how many players at this position)
        pos_count = len(roster[roster["Pos"] == row["Pos"]])
        ovr = int(row["OVR"])
        age = int(row["Age"])

        # ── Verdict Logic ──
        verdict = "KEEP"
        reason = ""

        # CUT candidates: low OVR + high dead cap + deep position
        if ovr < 72 and penalty > 5 and pos_count >= 3:
            verdict = "CUT"
            reason = f"Low OVR ({ovr}), ${penalty:.1f}M dead cap, {pos_count} deep at {row['Pos']}"
        elif ovr < 68 and pos_count >= 2:
            verdict = "CUT"
            reason = f"Below replacement level ({ovr} OVR)"
        # TRADE candidates: aging + replaceable + has value
        elif tv > 200 and age >= 29 and pos_count >= 2:
            verdict = "TRADE"
            reason = f"Aging ({age}yo), tradeable value ({tv:.0f}), backup available"
        elif tv > 300 and penalty > savings and age >= 27:
            verdict = "TRADE"
            reason = f"Cap negative (${penalty:.1f}M dead > ${savings:.1f}M sav), still has value"
        elif ovr >= 75 and age >= 31 and pos_count >= 2:
            verdict = "TRADE"
            reason = f"Veteran ({age}yo, {ovr} OVR), sell high before decline"
        # KEEP: everyone else (default)
        else:
            if ovr >= 85:
                reason = "Core player — franchise cornerstone"
            elif ovr >= 78:
                reason = "Solid contributor — good value"
            elif age <= 24 and str(row.get("Dev", "")).lower() in ("superstar", "x-factor", "star"):
                reason = "Young dev talent — high ceiling"
            else:
                reason = "Roster depth piece"

        results.append({
            "Name": row["Name"],
            "Pos": row["Pos"],
            "OVR": ovr,
            "Age": age,
            "Dev": str(row.get("Dev", "Normal")),
            "Trade_Value": round(tv, 1),
            "Savings": savings,
            "Penalty": penalty,
            "Depth": pos_count,
            "Verdict": verdict,
            "Reason": reason,
        })

    # Sort: CUT first, then TRADE, then KEEP
    order = {"CUT": 0, "TRADE": 1, "KEEP": 2}
    results.sort(key=lambda x: (order.get(x["Verdict"], 3), -x["Trade_Value"]))
    return results
