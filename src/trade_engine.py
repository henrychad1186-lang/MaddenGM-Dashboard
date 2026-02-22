"""
Trade Engine — Trade value calculations, partner finding, and counter-offers.
Loads real GB roster from data/packers_roster.csv when available.
"""

import os
import pandas as pd
import math

# ──────────────────────────────────────────────
# LOAD ROSTER DATA — Real CSV for GB + Demo for CPU teams
# ──────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_ROSTER_CSV = os.path.join(_DATA_DIR, "packers_roster.csv")

# CPU team demo rosters (for trade partner scanning)
_CPU_DEMO = [
    # ── Detroit Lions ──
    {"Team": "DET", "Name": "Jared Goff",        "Pos": "QB",
        "OVR": 86, "Age": 31, "Dev": "Star",        "Scheme": "Spread"},
    {"Team": "DET", "Name": "Jahmyr Gibbs",      "Pos": "HB",
        "OVR": 89, "Age": 24, "Dev": "Superstar X", "Scheme": "Spread"},
    {"Team": "DET", "Name": "Amon-Ra St. Brown", "Pos": "WR",
        "OVR": 92, "Age": 26, "Dev": "Superstar X", "Scheme": "Spread"},
    {"Team": "DET", "Name": "Sam LaPorta",       "Pos": "TE",
        "OVR": 85, "Age": 24, "Dev": "Superstar",   "Scheme": "Spread"},
    {"Team": "DET", "Name": "Aidan Hutchinson",  "Pos": "EDGE",
        "OVR": 91, "Age": 26, "Dev": "Superstar X", "Scheme": "Spread"},
    {"Team": "DET", "Name": "Brian Branch",      "Pos": "CB",
        "OVR": 84, "Age": 24, "Dev": "Superstar",   "Scheme": "Spread"},

    # ── Chicago Bears ──
    {"Team": "CHI", "Name": "Caleb Williams",    "Pos": "QB",  "OVR": 79,
        "Age": 23, "Dev": "Superstar X", "Scheme": "Vertical"},
    {"Team": "CHI", "Name": "D'Andre Swift",     "Pos": "HB",  "OVR": 83,
        "Age": 27, "Dev": "Star",        "Scheme": "Vertical"},
    {"Team": "CHI", "Name": "DJ Moore",          "Pos": "WR",  "OVR": 87,
        "Age": 29, "Dev": "Star",        "Scheme": "Vertical"},
    {"Team": "CHI", "Name": "Cole Kmet",         "Pos": "TE",  "OVR": 82,
        "Age": 27, "Dev": "Star",        "Scheme": "Vertical"},
    {"Team": "CHI", "Name": "Montez Sweat",      "Pos": "EDGE",
        "OVR": 88, "Age": 29, "Dev": "Star",        "Scheme": "Vertical"},
    {"Team": "CHI", "Name": "Jaylon Johnson",    "Pos": "CB",  "OVR": 86,
        "Age": 28, "Dev": "Star",        "Scheme": "Vertical"},

    # ── Minnesota Vikings ──
    {"Team": "MIN", "Name": "Sam Darnold",       "Pos": "QB",  "OVR": 82,
        "Age": 29, "Dev": "Star",        "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Aaron Jones",       "Pos": "HB",  "OVR": 84,
        "Age": 31, "Dev": "Normal",      "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Justin Jefferson",  "Pos": "WR",  "OVR": 99,
        "Age": 27, "Dev": "Superstar X", "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "T.J. Hockenson",    "Pos": "TE",  "OVR": 87,
        "Age": 28, "Dev": "Star",        "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Jonathan Greenard",  "Pos": "EDGE",
        "OVR": 87, "Age": 28, "Dev": "Star",        "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Byron Murphy Jr.",   "Pos": "CB",  "OVR": 83,
        "Age": 28, "Dev": "Star",        "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Harrison Smith",     "Pos": "SS",  "OVR": 81,
        "Age": 37, "Dev": "Normal",      "Scheme": "WestCoast"},
    {"Team": "MIN", "Name": "Ivan Pace Jr.",      "Pos": "MLB", "OVR": 78,
        "Age": 25, "Dev": "Star",        "Scheme": "WestCoast"},
]


def _load_trade_rosters() -> pd.DataFrame:
    """Load GB roster from CSV + CPU demo rosters."""
    cpu_df = pd.DataFrame(_CPU_DEMO)

    if os.path.exists(_ROSTER_CSV):
        gb_df = pd.read_csv(_ROSTER_CSV)
        # Ensure required columns
        if "Team" not in gb_df.columns:
            gb_df["Team"] = "GB"
        if "Scheme" not in gb_df.columns:
            gb_df["Scheme"] = "WestCoast"
        if "Dev" not in gb_df.columns:
            gb_df["Dev"] = "Normal"
        # Normalize REDG/LEDG → EDGE
        gb_df["Pos"] = gb_df["Pos"].replace({"REDG": "EDGE", "LEDG": "EDGE"})
        return pd.concat([gb_df, cpu_df], ignore_index=True)
    else:
        return cpu_df


DEMO_ROSTERS = _load_trade_rosters()

# Position weights for trade-value calculations
POSITION_WEIGHTS = {
    "QB": 1.35, "HB": 0.90, "WR": 1.10, "TE": 0.85,
    "LT": 1.05, "LG": 0.80, "C": 0.80, "RG": 0.80, "RT": 0.95,
    "EDGE": 1.15, "DT": 0.90, "MLB": 0.85, "OLB": 0.80,
    "CB": 1.10, "FS": 0.85, "SS": 0.80, "K": 0.40, "P": 0.35,
}

DEV_MULTIPLIERS = {
    "Superstar X": 1.30,
    "Superstar": 1.15,
    "Star": 1.05,
    "Normal": 1.00,
}

DRAFT_PICK_VALUES = [
    ("1st-Round Pick",  8500),
    ("2nd-Round Pick",  5500),
    ("3rd-Round Pick",  3500),
    ("4th-Round Pick",  2000),
    ("5th-Round Pick",  1200),
    ("6th-Round Pick",   700),
    ("7th-Round Pick",   350),
]


# ──────────────────────────────────────────────
# CORE FUNCTIONS
# ──────────────────────────────────────────────

def _parse_salary(val) -> float:
    """Convert salary strings like '$3M', '$1.29M', '$600K' to float millions."""
    if pd.isna(val) or val is None or str(val).strip() == "":
        return 0.0
    s = str(val).strip().replace("$", "").replace(",", "")
    try:
        if s.upper().endswith("M"):
            return float(s[:-1])
        elif s.upper().endswith("K"):
            return float(s[:-1]) / 1000.0
        else:
            return float(s)
    except (ValueError, TypeError):
        return 0.0


def get_trade_value(player: dict) -> float:
    """Calculate a trade-value score for a single player.

    Factors: OVR, position, age, dev trait, contract cap impact,
    and physical attributes (SPD/ACC/AGI).
    """
    ovr = player.get("OVR", 70)
    age = player.get("Age", 27)
    pos = player.get("Pos", "WR")
    dev = player.get("Dev", "Normal")

    # Base value scales exponentially with OVR
    base = (ovr ** 2) / 10.0

    # Position premium
    pos_weight = POSITION_WEIGHTS.get(pos, 0.85)
    base *= pos_weight

    # Position-specific age curves
    # (peak_start, peak_end, bonus_per_yr_under, penalty_per_yr_over, floor)
    _AGE_CURVES = {
        "QB":   (26, 32, 0.02, 0.03, 0.60),  # QBs age gracefully
        "HB":   (23, 27, 0.03, 0.07, 0.40),  # RBs cliff hard
        "WR":   (23, 28, 0.03, 0.06, 0.45),
        "TE":   (24, 30, 0.02, 0.04, 0.50),
        "LT":   (24, 31, 0.02, 0.04, 0.50),  # OL stays productive
        "LG":   (24, 31, 0.02, 0.04, 0.50),
        "C":    (24, 31, 0.02, 0.04, 0.50),
        "RG":   (24, 31, 0.02, 0.04, 0.50),
        "RT":   (24, 31, 0.02, 0.04, 0.50),
        "EDGE": (23, 29, 0.03, 0.05, 0.45),  # Pass rushers
        "REDG": (23, 29, 0.03, 0.05, 0.45),
        "LEDG": (23, 29, 0.03, 0.05, 0.45),
        "DT":   (24, 30, 0.02, 0.04, 0.50),
        "MLB":  (24, 29, 0.03, 0.05, 0.45),
        "OLB":  (24, 29, 0.03, 0.05, 0.45),
        "CB":   (23, 28, 0.03, 0.06, 0.40),  # CBs lose a step fast
        "FS":   (24, 29, 0.03, 0.05, 0.45),
        "SS":   (24, 29, 0.03, 0.05, 0.45),
        "K":    (24, 35, 0.01, 0.02, 0.70),  # Kickers age slowly
        "P":    (24, 35, 0.01, 0.02, 0.70),
    }
    # Default curve for unmapped positions
    peak_start, peak_end, bonus_yr, penalty_yr, floor = _AGE_CURVES.get(
        pos, (24, 29, 0.03, 0.05, 0.45))

    if age < peak_start:
        age_factor = 1.0 + (peak_start - age) * bonus_yr
    elif age <= peak_end:
        age_factor = 1.0  # in prime window
    else:
        age_factor = 1.0 - (age - peak_end) * penalty_yr
    age_factor = max(age_factor, floor)
    base *= age_factor

    # Development trait bonus
    dev_mult = DEV_MULTIPLIERS.get(dev, 1.0)
    base *= dev_mult

    # ── CONTRACT CAP IMPACT ──
    # Cap savings = team-friendly deal → more attractive to trade for
    # Dead-cap penalty = costly to cut/trade → reduces trade appeal
    savings = _parse_salary(player.get("Savings"))
    penalty = _parse_salary(player.get("Penalty"))

    if savings > 0 or penalty > 0:
        # Savings bonus: up to +8% for very cap-friendly deals (>$5M savings)
        savings_bonus = min(savings / 5.0, 1.0) * 0.08

        # Penalty drag: up to -12% for huge dead-cap hits (>$20M penalty)
        penalty_drag = min(penalty / 20.0, 1.0) * 0.12

        contract_factor = 1.0 + savings_bonus - penalty_drag
        contract_factor = max(contract_factor, 0.85)  # floor
        base *= contract_factor

    # ── PHYSICAL ATTRIBUTES BONUS ──
    # SPD, ACC, AGI complement OVR — elite athletes are worth more
    spd = player.get("SPD") or player.get("Speed")
    acc = player.get("ACC") or player.get("Acceleration")
    agi = player.get("AGI") or player.get("Agility")

    phys_ratings = [r for r in [spd, acc, agi]
                    if r is not None and not (isinstance(r, float) and math.isnan(r))]

    if phys_ratings:
        avg_phys = sum(float(r) for r in phys_ratings) / len(phys_ratings)
        # Bonus kicks in above 85, penalty below 75
        # Range: roughly -5% to +7%
        phys_factor = 1.0 + (avg_phys - 80) * 0.0015
        phys_factor = max(min(phys_factor, 1.07), 0.95)  # clamp
        base *= phys_factor

    return round(base, 1)


def find_trade_partners(player: dict, user_team: str = "GB") -> list[dict]:
    """
    Scan CPU teams for potential trade partners interested in the offered player.
    Returns a list of dicts: {team, interest, reason, scheme_fit, best_offer}.
    """
    offered_pos = player.get("Pos", "WR")
    offered_ovr = player.get("OVR", 70)
    offered_scheme = player.get("Scheme", "")

    partners = []
    for team in DEMO_ROSTERS["Team"].unique():
        if team == user_team:
            continue

        team_roster = DEMO_ROSTERS[DEMO_ROSTERS["Team"] == team]
        team_scheme = team_roster.iloc[0]["Scheme"] if len(
            team_roster) > 0 else ""

        # Check if position exists on team; if so, does offered player upgrade it?
        same_pos = team_roster[team_roster["Pos"] == offered_pos]

        if same_pos.empty:
            # Team has no one at this position — high interest
            interest = 90
            reason = f"No {offered_pos} on roster — fills critical need"
        else:
            best_on_team = same_pos["OVR"].max()
            gap = offered_ovr - best_on_team
            if gap > 5:
                interest = 85
                reason = f"Major upgrade (+{gap} OVR over current starter)"
            elif gap > 0:
                interest = 65
                reason = f"Moderate upgrade (+{gap} OVR)"
            elif gap > -3:
                interest = 40
                reason = "Depth move — similar caliber"
            else:
                interest = 15
                reason = "Downgrade — low interest"

        # Scheme-fit bonus
        scheme_fit = offered_scheme == team_scheme
        if scheme_fit:
            interest = min(interest + 12, 100)

        # Age penalty for older players
        offered_age = player.get("Age", 27)
        if offered_age >= 30:
            interest = max(interest - 10, 5)

        # Find the best player the CPU team could offer back
        non_qb = team_roster[team_roster["Pos"] != "QB"].copy()
        if non_qb.empty:
            non_qb = team_roster.copy()
        non_qb = non_qb.copy()
        non_qb["TradeVal"] = non_qb.apply(
            lambda r: get_trade_value(r.to_dict()), axis=1)
        best_offer_row = non_qb.sort_values(
            "TradeVal", ascending=False).iloc[0]

        partners.append({
            "team": team,
            "interest": interest,
            "reason": reason,
            "scheme_fit": scheme_fit,
            "best_offer_name": best_offer_row["Name"],
            "best_offer_pos": best_offer_row["Pos"],
            "best_offer_ovr": int(best_offer_row["OVR"]),
        })

    # Sort by interest descending
    partners.sort(key=lambda x: x["interest"], reverse=True)
    return partners


def generate_counter_offer(target_value: float, current_value: float) -> str:
    """
    Suggest draft picks or sweeteners to bridge a trade-value gap.
    Returns a human-readable suggestion string.
    """
    gap = target_value - current_value
    if gap <= 0:
        return "✅ Trade is already fair or favors you — no sweetener needed."

    suggestions = []
    remaining = gap
    for pick_name, pick_val in DRAFT_PICK_VALUES:
        if remaining <= 0:
            break
        if pick_val <= remaining * 1.4:  # allow slight overshoot
            suggestions.append(pick_name)
            remaining -= pick_val

    if not suggestions:
        return f"⚠️ Gap of {gap:.0f} is too small for a draft pick — consider adding a late-round swap."

    return "💡 Add **" + " + ".join(suggestions) + f"** to bridge the ~{gap:.0f} point gap."


def evaluate_trade(offered_players: list[dict], requested_players: list[dict]) -> dict:
    """
    Evaluate a trade. Returns dict with verdict, values, and counter-offer.
    """
    offered_val = sum(get_trade_value(p) for p in offered_players)
    requested_val = sum(get_trade_value(p) for p in requested_players)

    diff = offered_val - requested_val
    ratio = offered_val / max(requested_val, 1)

    if ratio >= 0.92:
        verdict = "✅ ACCEPTED"
        verdict_color = "green"
    elif ratio >= 0.80:
        verdict = "🤝 LEAN ACCEPT"
        verdict_color = "orange"
    else:
        verdict = "❌ DECLINED"
        verdict_color = "red"

    counter = generate_counter_offer(
        requested_val, offered_val) if ratio < 0.92 else ""

    return {
        "verdict": verdict,
        "verdict_color": verdict_color,
        "offered_value": round(offered_val, 1),
        "requested_value": round(requested_val, 1),
        "diff": round(diff, 1),
        "counter_offer": counter,
    }
