"""
AI GM Assistant — dynamically plug new players into the franchise and get
an AI-generated scouting report on the spot.

A rookie draft pick, UDFA signing, or trade acquisition can be entered
through the UI; this module validates it, injects it into the live roster
(`src.roster.ALL_ROSTERS`) and trade pool (`src.trade_engine.DEMO_ROSTERS`)
so it immediately shows up across Roster Explorer, Cap Overview, Cut/Keep,
the Depth Chart, and the Trade Machine, and returns a grade/strengths/
weaknesses/verdict writeup driven by the same heuristics the rest of the
app uses (trade value curve, positional need, dev traits, athleticism).
"""

import pandas as pd

from src import roster as roster_mod
from src import trade_engine as trade_mod
from src.trade_engine import get_trade_value

REQUIRED_FIELDS = ["Name", "Pos", "Age", "OVR"]
ATTR_FIELDS = ["SPD", "ACC", "AGI", "COD", "STR", "AWR"]
DEV_TRAITS = ["Normal", "Star", "Superstar", "Superstar X"]

_ATTR_LABELS = {
    "SPD": "Speed", "ACC": "Acceleration", "AGI": "Agility",
    "COD": "Change of Direction", "STR": "Strength", "AWR": "Awareness",
}


# ──────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────

def validate_player(player: dict) -> list[str]:
    """Return a list of validation error messages (empty list = valid)."""
    errors = []

    if not str(player.get("Name", "")).strip():
        errors.append("Name is required.")

    pos = str(player.get("Pos", "")).strip().upper()
    if not pos:
        errors.append("Position is required.")
    elif roster_mod.normalize_position(pos) not in roster_mod.VALID_POSITIONS:
        errors.append(f"Unrecognized position '{pos}'.")

    try:
        ovr = int(player.get("OVR"))
        if not (1 <= ovr <= 99):
            errors.append("OVR must be between 1 and 99.")
    except (TypeError, ValueError):
        errors.append("OVR must be a whole number.")

    try:
        age = int(player.get("Age"))
        if not (18 <= age <= 45):
            errors.append("Age must be between 18 and 45.")
    except (TypeError, ValueError):
        errors.append("Age must be a whole number.")

    for attr in ATTR_FIELDS:
        val = player.get(attr)
        if val in (None, ""):
            continue
        try:
            ival = int(val)
            if not (0 <= ival <= 99):
                errors.append(f"{attr} must be between 0 and 99.")
        except (TypeError, ValueError):
            errors.append(f"{attr} must be a whole number.")

    return errors


def _normalize(player: dict, team: str) -> dict:
    normalized = {
        "Name": str(player["Name"]).strip(),
        "Pos": roster_mod.normalize_position(str(player["Pos"])),
        "Age": int(player["Age"]),
        "OVR": int(player["OVR"]),
        "Team": team,
        "Dev": str(player.get("Dev") or "Normal"),
        "Savings": str(player.get("Savings") or "$0"),
        "Penalty": str(player.get("Penalty") or "$0"),
    }
    for attr in ATTR_FIELDS:
        val = player.get(attr)
        if val not in (None, ""):
            normalized[attr] = int(val)
    return normalized


# ──────────────────────────────────────────────
# POSITIONAL NEEDS
# ──────────────────────────────────────────────

def positional_needs(team: str) -> list[dict]:
    """Grade every starting position by depth + average OVR for a team."""
    df = roster_mod.get_roster(team, "All")
    needs = []
    for pos in roster_mod.POSITION_ORDER:
        pos_df = df[df["Pos"] == pos]
        count = len(pos_df)
        avg_ovr = round(pos_df["OVR"].mean(), 1) if count else 0.0

        if count == 0 or (count == 1 and avg_ovr < 78):
            level, color = "Critical", "#ff5252"
        elif avg_ovr < 78 or count == 2:
            level, color = "Moderate", "#ffc107"
        else:
            level, color = "Set", "#00e676"

        needs.append({
            "pos": pos, "count": count, "avg_ovr": avg_ovr,
            "level": level, "color": color,
        })
    return needs


# ──────────────────────────────────────────────
# SCOUTING REPORT
# ──────────────────────────────────────────────

def _attr_grade(val: float) -> str:
    if val >= 90:
        return "elite"
    elif val < 65:
        return "raw"
    return "average"


def _write_blurb(name, pos, tier, age, dev, strengths, weaknesses, need, verdict, reason, trade_value) -> str:
    s1 = (f"**{name}** grades out as a **{tier}** {pos} prospect, "
          f"age {age}, carrying a **{dev}** development trait.")

    if strengths:
        s2 = f"Testing pops at **{', '.join(strengths)}** — a plus trait for the position."
    else:
        s2 = "Athletic testing is unremarkable — more technician than workout warrior."

    if weaknesses:
        s3 = f"Areas of concern: **{', '.join(weaknesses)}** — will need coaching up."
    else:
        s3 = "No glaring athletic red flags in the profile."

    avg_txt = f"{need['avg_ovr']:.0f} avg OVR across {need['count']} player(s)" if need["count"] else "currently empty"
    s4 = (f"The {pos} room is rated **{need['level']}** ({avg_txt}); "
          f"this addition projects an estimated trade value of **{trade_value:,.0f}**.")

    s5 = f"**AI GM Verdict: {verdict}** — {reason}"

    return " ".join([s1, s2, s3, s4, s5])


def scout_player(player: dict, team: str) -> dict:
    """Generate an AI scouting report for a player against a team's roster.

    `player` is not required to already be on the roster — this can be
    called on a prospective add before it's committed.
    """
    pos = roster_mod.normalize_position(str(player.get("Pos", "")))
    ovr = int(player.get("OVR", 0))
    age = int(player.get("Age", 0))
    dev = str(player.get("Dev", "Normal"))

    trade_value = get_trade_value({**player, "Pos": pos})

    needs = {n["pos"]: n for n in positional_needs(team)}
    need = needs.get(pos, {"pos": pos, "count": 0, "avg_ovr": 0.0,
                           "level": "Moderate", "color": "#ffc107"})

    strengths, weaknesses = [], []
    for attr, label in _ATTR_LABELS.items():
        val = player.get(attr)
        if val in (None, ""):
            continue
        val = float(val)
        grade = _attr_grade(val)
        if grade == "elite":
            strengths.append(f"{label} ({val:.0f})")
        elif grade == "raw":
            weaknesses.append(f"{label} ({val:.0f})")

    tier = roster_mod.ovr_label(ovr)

    upgrades_starter = need["count"] > 0 and ovr > need["avg_ovr"] + 3
    is_young_dev = age <= 23 and dev in ("Star", "Superstar", "Superstar X")

    if need["level"] == "Critical" and ovr >= 65:
        verdict, verdict_color = "SIGN — Fills Critical Need", "#00e676"
        reason = f"{pos} room is thin ({need['count']} on roster) — immediate roster spot."
    elif upgrades_starter:
        verdict, verdict_color = "SIGN & START", "#00e676"
        reason = f"Beats the current {pos} average ({need['avg_ovr']:.0f} OVR) — plug-and-play starter."
    elif is_young_dev:
        verdict, verdict_color = "SIGN & DEVELOP", "#2196f3"
        reason = f"Age {age} with a {dev} dev trait — stash for long-term upside."
    elif ovr >= 72:
        verdict, verdict_color = "ROTATIONAL DEPTH", "#ffc107"
        reason = "Solid depth piece, not an immediate starter."
    else:
        verdict, verdict_color = "PASS", "#ff5252"
        reason = f"Below replacement level for a {need['level'].lower()}-need position."

    blurb = _write_blurb(player.get("Name", "This player"), pos, tier, age, dev,
                         strengths, weaknesses, need, verdict, reason, trade_value)

    return {
        "Name": player.get("Name", "Unnamed"),
        "Pos": pos, "OVR": ovr, "Age": age, "Dev": dev,
        "tier": tier, "trade_value": trade_value,
        "pos_avg_ovr": need["avg_ovr"], "pos_count": need["count"],
        "need_level": need["level"],
        "strengths": strengths, "weaknesses": weaknesses,
        "verdict": verdict, "verdict_color": verdict_color, "reason": reason,
        "blurb": blurb,
    }


# ──────────────────────────────────────────────
# DYNAMIC ROSTER INJECTION
# ──────────────────────────────────────────────

def add_player(player: dict, team: str, persist: bool = False) -> dict:
    """Validate a player and inject them into the live roster + trade pool.

    Returns {"ok": bool, "errors": [...], "player": normalized dict|None}.
    On success, `src.roster.ALL_ROSTERS` and `src.trade_engine.DEMO_ROSTERS`
    are updated in place so every tab that reads them picks the player up
    on the next Streamlit rerun. When `persist` is True, the team's roster
    is also written back to `data/packers_roster.csv` (best-effort — silently
    skipped on read-only filesystems like Streamlit Cloud).
    """
    errors = validate_player(player)
    if errors:
        return {"ok": False, "errors": errors, "player": None}

    normalized = _normalize(player, team)

    roster_row = dict(normalized)
    roster_row["Group"] = roster_mod.assign_group(normalized["Pos"])
    roster_mod.ALL_ROSTERS = pd.concat(
        [roster_mod.ALL_ROSTERS, pd.DataFrame([roster_row])], ignore_index=True)

    trade_row = dict(normalized)
    trade_row["Scheme"] = trade_mod.DEMO_ROSTERS.loc[
        trade_mod.DEMO_ROSTERS["Team"] == team, "Scheme"
    ].iloc[0] if (trade_mod.DEMO_ROSTERS["Team"] == team).any() else "WestCoast"
    trade_mod.DEMO_ROSTERS = pd.concat(
        [trade_mod.DEMO_ROSTERS, pd.DataFrame([trade_row])], ignore_index=True)

    if persist:
        try:
            roster_mod.ALL_ROSTERS.drop(columns=["Group"], errors="ignore").to_csv(
                roster_mod._ROSTER_CSV, index=False)
        except OSError:
            pass  # read-only filesystem — player still lives in memory

    return {"ok": True, "errors": [], "player": normalized}


def remove_player(name: str, team: str) -> bool:
    """Remove a player by exact name from the live roster + trade pool."""
    before = len(roster_mod.ALL_ROSTERS)
    roster_mod.ALL_ROSTERS = roster_mod.ALL_ROSTERS[
        ~((roster_mod.ALL_ROSTERS["Team"] == team) & (roster_mod.ALL_ROSTERS["Name"] == name))
    ].reset_index(drop=True)
    trade_mod.DEMO_ROSTERS = trade_mod.DEMO_ROSTERS[
        ~((trade_mod.DEMO_ROSTERS["Team"] == team) & (trade_mod.DEMO_ROSTERS["Name"] == name))
    ].reset_index(drop=True)
    return len(roster_mod.ALL_ROSTERS) < before
