"""
Cut or Keep Analyzer — evaluate each player's roster status.

Combines trade value, cap savings/penalties, positional depth, age,
and OVR to recommend: KEEP / TRADE / CUT for every player.
"""

from src.roster import get_roster, get_cap_summary
from src.trade_engine import get_trade_value


def analyze_roster(team: str) -> list[dict]:
    """Return a list of player analysis dicts with verdicts.

    Each dict contains:
        Name, Pos, OVR, Age, Dev, Trade_Value, Savings, Penalty,
        Depth, Verdict, Verdict_Reason
    """
    roster = get_roster(team, "All")
    if roster.empty:
        return []
    cap = get_cap_summary(team)
    # Build cap lookup
    cap_lookup = {p["Name"]: p for p in cap["players"]}
    # Precompute positional depth counts once instead of filtering per player.
    pos_counts = roster["Pos"].value_counts().to_dict()
    players = roster.to_dict("records")
    trade_values = [get_trade_value(player) for player in players]

    results = []
    for player, tv in zip(players, trade_values):
        cap_info = cap_lookup.get(player["Name"], {"Savings": 0, "Penalty": 0})
        savings = cap_info["Savings"]
        penalty = cap_info["Penalty"]

        # Count positional depth (how many players at this position)
        pos = player["Pos"]
        pos_count = int(pos_counts.get(pos, 0))
        ovr = int(player["OVR"])
        age = int(player["Age"])

        # ── Verdict Logic ──
        verdict = "KEEP"
        reason = ""

        # CUT candidates: low OVR + high dead cap + deep position
        if ovr < 72 and penalty > 5 and pos_count >= 3:
            verdict = "CUT"
            reason = f"Low OVR ({ovr}), ${penalty:.1f}M dead cap, {pos_count} deep at {pos}"
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
            elif age <= 24 and str(player.get("Dev", "")).lower() in ("superstar", "x-factor", "star"):
                reason = "Young dev talent — high ceiling"
            else:
                reason = "Roster depth piece"

        results.append({
            "Name": player["Name"],
            "Pos": pos,
            "OVR": ovr,
            "Age": age,
            "Dev": str(player.get("Dev", "Normal")),
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
