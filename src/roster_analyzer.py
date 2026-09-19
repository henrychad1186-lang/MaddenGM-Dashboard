"""
Cut or Keep Analyzer — evaluate each player's roster status.

Combines trade value, cap savings/penalties, positional depth, age,
and OVR to recommend: KEEP / TRADE / CUT for every player.
"""

from collections import defaultdict

from src.roster import get_roster, get_cap_summary
from src.trade_engine import get_trade_value


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

    # cap["players"] is sorted by Penalty and can't be zipped positionally
    # against `roster`. A plain {Name: entry} dict would let same-named
    # players (AI GM explicitly allows duplicate names) silently overwrite
    # each other's cap lookup. Instead keep a per-name queue and consume
    # the best Pos+OVR match for each roster row, so duplicates each get
    # paired with their own cap entry instead of all sharing the last one.
    cap_by_name = defaultdict(list)
    for p in cap["players"]:
        cap_by_name[p["Name"]].append(p)

    # Positional depth, counted once. This used to be
    # `len(roster[roster["Pos"] == row["Pos"]])` inside the loop, which
    # builds a full boolean mask over the roster for every player — O(n^2)
    # scans to answer n questions that one pass already answers.
    pos_counts = roster["Pos"].value_counts().to_dict()

    # `to_dict("records")` in place of `iterrows()`, which allocates a
    # Series per row before the dict conversion. Row order is preserved,
    # which the cap queue below depends on.
    players = roster.to_dict("records")

    results = []
    for player in players:
        tv = get_trade_value(player)

        candidates = cap_by_name.get(player["Name"], [])
        if candidates:
            match_idx = next(
                (i for i, c in enumerate(candidates)
                 if c["Pos"] == player["Pos"] and c["OVR"] == int(player["OVR"])),
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

        # ── Verdict Logic ──
        verdict = "KEEP"
        reason = ""

        # CUT candidates: low OVR + net cap savings from cutting + deep position
        if ovr < 72 and savings > penalty and pos_count >= 3:
            verdict = "CUT"
            reason = f"Low OVR ({ovr}), net ${savings - penalty:.1f}M cap relief, {pos_count} deep at {pos}"
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
            elif age <= 24 and str(player.get("Dev", "")).lower() in ("superstar", "superstar x", "star"):
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
