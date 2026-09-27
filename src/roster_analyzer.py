"""
Cut or Keep Analyzer — evaluate each player's roster status.

Combines trade value, cap savings/penalties, positional depth, age,
and OVR to recommend: KEEP / TRADE / CUT for every player.
"""

from collections import defaultdict

from src.roster import get_roster, get_cap_summary
from src.trade_engine import age_curve, get_trade_value


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
        # In Madden franchise mode a trade charges the same remaining-bonus
        # dead cap as a release, so `penalty` is the cost of moving a
        # player either way and `savings - penalty` is the net cap effect
        # of any move. An earlier rule read "dead cap > savings" as a
        # reason to TRADE, which is backwards: it flagged 12 of 37 GB
        # players, including the only QB and a 98 OVR 27-year-old.
        verdict = "KEEP"
        reason = ""
        net_cap = savings - penalty
        peak_end = age_curve(pos)[1]
        past_peak = age > peak_end
        has_backup = pos_count >= 2
        core = ovr >= 85 and not past_peak

        # CUT candidates: low OVR + net cap savings from cutting + deep position
        if ovr < 72 and net_cap > 0 and pos_count >= 3:
            verdict = "CUT"
            reason = f"Low OVR ({ovr}), net ${net_cap:.1f}M cap relief, {pos_count} deep at {pos}"
        elif ovr < 68 and has_backup and net_cap >= 0:
            verdict = "CUT"
            reason = f"Below replacement level ({ovr} OVR)"
        # TRADE candidates: past this position's age peak, still a
        # starter-grade player, a backup behind him, and moving him
        # doesn't cost more cap than it frees.
        elif (past_peak and ovr >= 75 and has_backup and not core
              and net_cap >= 0):
            verdict = "TRADE"
            reason = (f"Past {pos} peak ({age}yo, peak ends {peak_end}), {ovr} OVR — "
                      f"sell before decline, frees ${net_cap:.1f}M")
        # KEEP: everyone else (default)
        else:
            if core:
                reason = "Core player — franchise cornerstone"
            elif past_peak and ovr >= 75 and net_cap < 0:
                reason = (f"Past peak, but ${penalty:.1f}M dead cap vs ${savings:.1f}M "
                          f"saved if moved — ride out the contract")
            elif not has_backup and ovr >= 70:
                reason = f"Only {pos} on the roster — no replacement"
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
