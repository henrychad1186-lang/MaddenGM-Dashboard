"""
Cut or Keep Analyzer — evaluate each player's roster status.

Combines trade value, cap savings/penalties, positional depth, age,
and OVR to recommend: KEEP / TRADE / CUT for every player.
"""

from collections import defaultdict

from src.roster import get_roster, get_cap_summary
from src.trade_engine import get_trade_value



def _get_roster_verdict(
    *,
    age: int,
    ovr: int,
    penalty: float,
    pos: str,
    pos_count: int,
    savings: float,
    trade_value: float,
    dev_trait: str,
) -> tuple[str, str]:
    """Return the recommended roster verdict and supporting reason."""
    if ovr < 72 and penalty > 5 and pos_count >= 3:
        return "CUT", f"Low OVR ({ovr}), ${penalty:.1f}M dead cap, {pos_count} deep at {pos}"
    if ovr < 68 and pos_count >= 2:
        return "CUT", f"Below replacement level ({ovr} OVR)"
    if trade_value > 200 and age >= 29 and pos_count >= 2:
        return "TRADE", f"Aging ({age}yo), tradeable value ({trade_value:.0f}), backup available"
    if trade_value > 300 and penalty > savings and age >= 27:
        return "TRADE", f"Cap negative (${penalty:.1f}M dead > ${savings:.1f}M sav), still has value"
    if ovr >= 75 and age >= 31 and pos_count >= 2:
        return "TRADE", f"Veteran ({age}yo, {ovr} OVR), sell high before decline"
    if ovr >= 85:
        return "KEEP", "Core player — franchise cornerstone"
    if ovr >= 78:
        return "KEEP", "Solid contributor — good value"
    if age <= 24 and dev_trait in ("superstar", "superstar x", "x-factor", "star"):
        return "KEEP", "Young dev talent — high ceiling"
    return "KEEP", "Roster depth piece"



def analyze_roster(team: str, extra_players: "list[dict] | None" = None) -> list[dict]:
    """Return a list of player analysis dicts with verdicts.

    Each dict contains:
        Name, Pos, OVR, Age, Dev, Trade_Value, Savings, Penalty,
        Depth, Verdict, Verdict_Reason
    """
    roster = get_roster(team, "All", extra_players)
    if roster.empty:
        return []

    cap = get_cap_summary(team, extra_players)
    cap_by_name = defaultdict(list)
    for player in cap["players"]:
        cap_by_name[player["Name"]].append(player)

    pos_counts = roster["Pos"].value_counts().to_dict()
    players = roster.to_dict("records")
    trade_values = [get_trade_value(player) for player in players]

    results = []
    for player, tv in zip(players, trade_values):
        candidates = cap_by_name.get(player["Name"], [])
        if candidates:
            match_idx = next(
                (
                    i
                    for i, candidate in enumerate(candidates)
                    if candidate["Pos"] == player["Pos"]
                    and candidate["OVR"] == int(player["OVR"])
                ),
                0,
            )
            cap_info = candidates.pop(match_idx)
        else:
            cap_info = {"Savings": 0, "Penalty": 0}

        savings = cap_info["Savings"]
        penalty = cap_info["Penalty"]
        pos = player["Pos"]
        pos_count = int(pos_counts.get(pos, 0))
        ovr = int(player["OVR"])
        age = int(player["Age"])

        verdict, reason = _get_roster_verdict(
            age=age,
            ovr=ovr,
            penalty=penalty,
            pos=pos,
            pos_count=pos_count,
            savings=savings,
            trade_value=tv,
            dev_trait=str(player.get("Dev", "")).lower(),
        )

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

    order = {"CUT": 0, "TRADE": 1, "KEEP": 2}
    results.sort(key=lambda item: (order.get(item["Verdict"], 3), -item["Trade_Value"]))
    return results
