"""
Draft scouting: turn combine / pro day numbers and revealed letter grades
into rating estimates, then rank prospects on the attributes that matter
for each position.

Where the defaults come from
----------------------------
Every threshold below is community research from Madden 21-26 (Madden
School, Operation Sports). None of it is confirmed for Madden 27, so it
is all data in DEFAULT_RULES, editable in the tab and saved alongside the
prospect board, not constants in the code. Each estimate says how firm
it is:

  chart / anchor   inside the range the research actually measured
  extrapolated     outside it, following the same slope
  assumed          the research gave one data point; the slope is ours

The calibration step (actual ratings entered after the draft next to the
prediction) is how these get replaced with Madden 27 numbers.

What the research says, and what the defaults encode:
  - Speed follows the 40 time itself, not the player's rank in the
    class: 4.24 = 99 ... 4.49 = 90, about a point per 0.025-0.03s, with
    +/-2 of noise (a 4.51 has come out anywhere from 87 to 91).
  - The 3-cone reflects Acceleration and Agility; 6.60-6.83 maps to
    90-99 Agility. It does not measure Change of Direction.
  - The 20-yard shuttle splits points between Agility (weighted more)
    and COD (weighted less): a 4.17 is about 178 points, ~89/89.
  - Bench reps drive Strength, adjusted for arm length: 38 reps with
    32-inch arms was a 97.
  - Letter grades mean the same range for every attribute; A- = 82-85
    is the only range confirmed. Grades narrow as scouting progresses
    (A-C -> A).
"""

import copy
import json
import math
import os
import re

import pandas as pd

from src.roster_csv import normalize_position

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PROSPECTS_CSV = os.path.join(_DATA_DIR, "draft_prospects.csv")
RULES_JSON = os.path.join(_DATA_DIR, "draft_rules.json")

PROSPECT_COLUMNS = [
    "Name", "Pos", "Forty", "Bench", "Arm_In", "Three_Cone", "Shuttle",
    "Grades", "Notes",
    # Filled in after the draft, from the player's real ratings.
    "Actual_SPD", "Actual_AGI", "Actual_COD", "Actual_STR",
]
_NUMERIC_COLUMNS = ["Forty", "Bench", "Arm_In", "Three_Cone", "Shuttle",
                    "Actual_SPD", "Actual_AGI", "Actual_COD", "Actual_STR"]

# Attributes the combine estimates, as opposed to ones scouting reveals.
PHYSICAL_ATTRS = ("SPD", "AGI", "COD", "STR")

DEFAULT_RULES = {
    "speed_chart": [[4.24, 99], [4.27, 98], [4.30, 97], [4.32, 96], [4.35, 95],
                    [4.38, 94], [4.41, 93], [4.43, 92], [4.46, 91], [4.49, 90]],
    "speed_band": 2,
    "speed_safe_max": 4.43,       # at or under: 90+ Speed even at the low end
    "speed_coinflip_max": 4.49,   # up to here: 90 is inside the band
    "three_cone": {"fast": 6.60, "fast_agi": 99, "slow": 6.83, "slow_agi": 90},
    "shuttle": {"anchor_time": 4.17, "anchor_total": 178, "points_per_sec": 60},
    "bench": {"anchor_reps": 38, "anchor_arm": 32.0, "anchor_str": 97,
              "ref_arm": 33.0, "str_per_rep": 1.0},
    # Only A- is confirmed. The rest continue its 4-point width.
    "grades": [
        {"grade": "A+", "low": 90, "high": 99, "confirmed": False},
        {"grade": "A", "low": 86, "high": 89, "confirmed": False},
        {"grade": "A-", "low": 82, "high": 85, "confirmed": True},
        {"grade": "B+", "low": 78, "high": 81, "confirmed": False},
        {"grade": "B", "low": 74, "high": 77, "confirmed": False},
        {"grade": "B-", "low": 70, "high": 73, "confirmed": False},
        {"grade": "C+", "low": 66, "high": 69, "confirmed": False},
        {"grade": "C", "low": 62, "high": 65, "confirmed": False},
        {"grade": "C-", "low": 58, "high": 61, "confirmed": False},
        {"grade": "D+", "low": 54, "high": 57, "confirmed": False},
        {"grade": "D", "low": 50, "high": 53, "confirmed": False},
        {"grade": "D-", "low": 46, "high": 49, "confirmed": False},
        {"grade": "F", "low": 0, "high": 45, "confirmed": False},
    ],
    # A core grade whose floor reaches this is an A-tier reveal.
    "a_tier_floor": 82,
    # Scheme-dependent: edit to match the playbook.
    "core_attrs": {
        "QB": ["THP", "SAC", "MAC", "DAC", "TUP"],
        "HB": ["SPD", "AGI", "BCV", "ELU", "CAR"],
        "FB": ["RBK", "IBL", "CTH", "STR"],
        "WR": ["SPD", "RLS", "SRR", "MRR", "DRR", "CTH"],
        "TE": ["SPD", "CTH", "MRR", "RBK"],
        "LT": ["PBK", "PBP", "PBF", "STR"],
        "RT": ["PBK", "PBP", "PBF", "STR"],
        "LG": ["STR", "RBK", "RBP", "PBK"],
        "RG": ["STR", "RBK", "RBP", "PBK"],
        "C": ["STR", "RBK", "PBK", "AWR"],
        "EDGE": ["SPD", "PMV", "FMV", "BSH"],
        "DT": ["STR", "BSH", "PMV", "FMV"],
        "OLB": ["SPD", "PUR", "TAK", "ZCV"],
        "MLB": ["PUR", "TAK", "ZCV", "PRC"],
        "CB": ["SPD", "AGI", "MCV", "ZCV", "PRS"],
        "FS": ["SPD", "ZCV", "PRC", "TAK"],
        "SS": ["SPD", "ZCV", "PRC", "TAK"],
        "K": ["KPW", "KAC"],
        "P": ["KPW", "KAC"],
    },
}

# Positions whose Speed tier is flagged on the board.
SPEED_POSITIONS = {"CB", "WR", "HB"}


# ──────────────────────────────────────────────
# RULES
# ──────────────────────────────────────────────

def default_rules() -> dict:
    return copy.deepcopy(DEFAULT_RULES)


def _num(v) -> "float | None":
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def clean_rules(raw) -> dict:
    """Defaults overlaid with whatever in `raw` is well-formed.

    The rules file is hand-editable and uploadable, so each key is
    checked on its own: one bad entry falls back to its default instead
    of discarding the rest.
    """
    rules = default_rules()
    if not isinstance(raw, dict):
        return rules

    chart = raw.get("speed_chart")
    if isinstance(chart, list):
        pts = []
        for p in chart:
            if isinstance(p, (list, tuple)) and len(p) == 2:
                t, r = _num(p[0]), _num(p[1])
                if t is not None and r is not None and t > 0:
                    pts.append([t, r])
        # Two points make a line, and a repeated time would divide by
        # zero in estimate_speed (it interpolates between neighbours).
        # Requiring two distinct times wasn't enough: [[4.24, 99],
        # [4.24, 98], [4.30, 97]] passed and crashed the Draft tab for
        # any prospect at or under 4.24. Keep the first rating per time.
        by_time = {}
        for t, r in pts:
            by_time.setdefault(t, r)
        if len(by_time) >= 2:
            rules["speed_chart"] = sorted([t, r] for t, r in by_time.items())

    for key in ("speed_band", "speed_safe_max", "speed_coinflip_max", "a_tier_floor"):
        v = _num(raw.get(key))
        if v is not None and v >= 0:
            rules[key] = v

    for key in ("three_cone", "shuttle", "bench"):
        sub = raw.get(key)
        if isinstance(sub, dict):
            for k in rules[key]:
                v = _num(sub.get(k))
                if v is not None:
                    rules[key][k] = v
    if rules["three_cone"]["fast"] == rules["three_cone"]["slow"]:
        rules["three_cone"] = copy.deepcopy(DEFAULT_RULES["three_cone"])
    if rules["bench"]["ref_arm"] <= 0:
        rules["bench"]["ref_arm"] = DEFAULT_RULES["bench"]["ref_arm"]

    grades = raw.get("grades")
    if isinstance(grades, list):
        clean = []
        for g in grades:
            if not isinstance(g, dict):
                continue
            name = str(g.get("grade", "")).strip().upper()
            lo, hi = _num(g.get("low")), _num(g.get("high"))
            if re.fullmatch(r"[A-DF][+-]?", name) and lo is not None and hi is not None and lo <= hi:
                clean.append({"grade": name, "low": lo, "high": hi,
                              "confirmed": bool(g.get("confirmed", False))})
        if clean:
            rules["grades"] = clean

    core = raw.get("core_attrs")
    if isinstance(core, dict):
        clean = {}
        for pos, attrs in core.items():
            if isinstance(attrs, list):
                a = [str(x).strip().upper() for x in attrs if str(x).strip()]
                if a:
                    clean[normalize_position(pos)] = a
        if clean:
            rules["core_attrs"] = clean
    return rules


def load_rules(path: str = RULES_JSON) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return clean_rules(json.load(fh))
    except (OSError, ValueError):
        return default_rules()


def save_rules(rules: dict, path: str = RULES_JSON) -> bool:
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rules, fh, indent=1)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# ──────────────────────────────────────────────
# PROSPECT BOARD
# ──────────────────────────────────────────────

def empty_board() -> pd.DataFrame:
    return clean_board(pd.DataFrame(columns=PROSPECT_COLUMNS))


def clean_board(df: pd.DataFrame) -> pd.DataFrame:
    """Board in canonical shape: every column present, numbers numeric,
    blank-name rows dropped. Unknown columns are kept at the end."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in PROSPECT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    for col in _NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("Name", "Pos", "Grades", "Notes"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["Pos"] = df["Pos"].apply(lambda p: normalize_position(p) if p else "")
    df = df[df["Name"] != ""]
    extra = [c for c in df.columns if c not in PROSPECT_COLUMNS]
    return df[PROSPECT_COLUMNS + extra].reset_index(drop=True)


def load_board(path: str = PROSPECTS_CSV) -> pd.DataFrame:
    try:
        return clean_board(pd.read_csv(path))
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return empty_board()


def save_board(df: pd.DataFrame, path: str = PROSPECTS_CSV) -> bool:
    try:
        clean_board(df).to_csv(path, index=False)
        return True
    except OSError:
        return False


# ──────────────────────────────────────────────
# ESTIMATES
# ──────────────────────────────────────────────

def _clamp(v: float) -> float:
    return max(0.0, min(99.0, v))


def estimate_speed(forty, rules: dict) -> "dict | None":
    """Speed from the 40 time: {est, low, high, tier, basis}."""
    t = _num(forty)
    if t is None or t <= 0:
        return None
    chart = rules["speed_chart"]
    if t <= chart[0][0]:
        (t0, r0), (t1, r1) = chart[0], chart[1]
        basis = "chart" if t == chart[0][0] else "extrapolated"
    elif t >= chart[-1][0]:
        (t0, r0), (t1, r1) = chart[-2], chart[-1]
        basis = "chart" if t == chart[-1][0] else "extrapolated"
    else:
        basis = "chart"
        for (t0, r0), (t1, r1) in zip(chart, chart[1:]):
            if t0 <= t <= t1:
                break
    est = r0 + (t - t0) * (r1 - r0) / (t1 - t0)
    band = rules["speed_band"]
    if t <= rules["speed_safe_max"]:
        tier = "90+ safe"
    elif t <= rules["speed_coinflip_max"]:
        tier = "90 coin flip"
    else:
        tier = "under 90"
    return {"est": round(_clamp(est)), "low": round(_clamp(est - band)),
            "high": round(_clamp(est + band)), "tier": tier, "basis": basis}


def estimate_agility(three_cone, rules: dict) -> "dict | None":
    """Agility from the 3-cone (which also carries Acceleration, so a
    player with unusual burst will read off)."""
    t = _num(three_cone)
    if t is None or t <= 0:
        return None
    c = rules["three_cone"]
    slope = (c["slow_agi"] - c["fast_agi"]) / (c["slow"] - c["fast"])
    est = c["fast_agi"] + (t - c["fast"]) * slope
    lo_t, hi_t = sorted((c["fast"], c["slow"]))
    basis = "chart" if lo_t <= t <= hi_t else "extrapolated"
    return {"est": round(_clamp(est)), "basis": basis}


def estimate_cod(shuttle, agility_est: "float | None", rules: dict) -> "dict | None":
    """COD from the shuttle's total Agility + COD points, minus the
    3-cone's Agility estimate when there is one (a high-Agility player
    gets the same shuttle time with less COD); an even split otherwise."""
    t = _num(shuttle)
    if t is None or t <= 0:
        return None
    s = rules["shuttle"]
    total = s["anchor_total"] + (s["anchor_time"] - t) * s["points_per_sec"]
    cod = total - agility_est if agility_est is not None else total / 2
    basis = "anchor" if abs(t - s["anchor_time"]) <= 0.02 else "assumed"
    return {"est": round(_clamp(cod)), "total": round(total), "basis": basis,
            "split": "vs 3-cone AGI" if agility_est is not None else "even split"}


def estimate_strength(bench, arm, rules: dict) -> "dict | None":
    """Strength from bench reps scaled by arm length: a longer arm moves
    the bar further per rep, so the same count is worth more."""
    reps = _num(bench)
    if reps is None or reps < 0:
        return None
    b = rules["bench"]
    arm_in = _num(arm)
    adj = reps * (arm_in if arm_in and arm_in > 0 else b["ref_arm"]) / b["ref_arm"]
    anchor_adj = b["anchor_reps"] * b["anchor_arm"] / b["ref_arm"]
    est = b["anchor_str"] + (adj - anchor_adj) * b["str_per_rep"]
    return {"est": round(_clamp(est)), "adj_reps": round(adj, 1),
            "basis": "assumed" if arm_in else "assumed, no arm length"}


# ──────────────────────────────────────────────
# LETTER GRADES
# ──────────────────────────────────────────────

_GRADE = r"[A-DF][+-]?"
_RANGE_SEP = re.compile(r"\s*(?:\bto\b|~|–|—|/|\.\.)\s*", re.IGNORECASE)


def grade_range(text, rules: dict) -> "dict | None":
    """'A-' or a scouted range ('A to C', 'A-C', 'A~C', 'B+/A-') ->
    {low, high, confirmed}. None if it isn't a grade."""
    s = str(text or "").strip().upper().replace(" ", "")
    if not s:
        return None
    parts = [p for p in _RANGE_SEP.split(s.replace("TO", " TO ")) if p]
    if len(parts) == 1:
        m = re.fullmatch(f"({_GRADE})-({_GRADE})", parts[0])
        parts = [m.group(1), m.group(2)] if m else parts
    table = {g["grade"]: g for g in rules["grades"]}
    rows = [table.get(p) for p in parts]
    if not rows or any(r is None for r in rows) or len(rows) > 2:
        return None
    return {"low": min(r["low"] for r in rows), "high": max(r["high"] for r in rows),
            "confirmed": all(r["confirmed"] for r in rows)}


def parse_grades(text) -> "dict[str, str]":
    """'MCV:A-; PRS:A to C, zcv=B' -> {'MCV': 'A-', 'PRS': 'A to C', 'ZCV': 'B'}."""
    out = {}
    for item in re.split(r"[;,\n]", str(text or "")):
        if ":" in item:
            k, v = item.split(":", 1)
        elif "=" in item:
            k, v = item.split("=", 1)
        else:
            continue
        k, v = k.strip().upper(), v.strip()
        if k and v:
            out[k] = v
    return out


# ──────────────────────────────────────────────
# EVALUATION
# ──────────────────────────────────────────────

def evaluate_prospect(row, rules: dict) -> dict:
    """One board row -> estimates, core-attribute read and scouting priority."""
    pos = normalize_position(row.get("Pos", "")) if row.get("Pos") else ""
    spd = estimate_speed(row.get("Forty"), rules)
    agi = estimate_agility(row.get("Three_Cone"), rules)
    cod = estimate_cod(row.get("Shuttle"), agi["est"] if agi else None, rules)
    strn = estimate_strength(row.get("Bench"), row.get("Arm_In"), rules)
    physical = {"SPD": spd, "AGI": agi, "COD": cod, "STR": strn}

    grades = parse_grades(row.get("Grades"))
    ranges, bad = {}, []
    for attr, g in grades.items():
        r = grade_range(g, rules)
        if r:
            ranges[attr] = r
        else:
            bad.append(f"{attr}:{g}")

    core = rules["core_attrs"].get(pos, [])
    floor = rules["a_tier_floor"]
    values, a_confirmed, a_possible = [], [], []
    for attr in core:
        if attr in ranges:
            r = ranges[attr]
            values.append((r["low"] + r["high"]) / 2)
            if r["low"] >= floor:
                a_confirmed.append(attr)
            elif r["high"] >= floor:
                a_possible.append(attr)
        elif attr in PHYSICAL_ATTRS and physical[attr]:
            values.append(physical[attr]["est"])

    if a_confirmed:
        priority = "Scout now"
    elif a_possible:
        priority = "Narrow grades"
    elif core and not any(a in ranges for a in core if a not in PHYSICAL_ATTRS):
        priority = "Unscouted"
    else:
        priority = "Low"

    flags = []
    if pos in SPEED_POSITIONS and spd and spd["tier"] == "under 90":
        flags.append("sub-90 speed")
    if bad:
        flags.append("unreadable grade: " + ", ".join(bad))
    if not core and pos:
        flags.append(f"no core attributes set for {pos}")

    return {
        "Name": row.get("Name", ""), "Pos": pos,
        "SPD": spd["est"] if spd else None,
        "SPD_Range": f"{spd['low']}-{spd['high']}" if spd else "",
        "Speed_Tier": spd["tier"] if spd else "",
        "AGI": agi["est"] if agi else None,
        "COD": cod["est"] if cod else None,
        "STR": strn["est"] if strn else None,
        "Core_Fit": round(sum(values) / len(values), 1) if values else None,
        "Core_Known": f"{len(values)}/{len(core)}" if core else "",
        "A_Tier_Core": ", ".join(a_confirmed),
        "Maybe_A_Tier": ", ".join(a_possible),
        "Priority": priority,
        "Basis": "; ".join(f"{k} {v['basis']}" for k, v in physical.items() if v),
        "Flags": "; ".join(flags),
    }


_PRIORITY_ORDER = {"Scout now": 0, "Narrow grades": 1, "Unscouted": 2, "Low": 3}


def evaluate_board(board: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Evaluate every prospect, best scouting targets first."""
    if board is None or board.empty:
        return pd.DataFrame()
    rows = [evaluate_prospect(r, rules) for r in board.to_dict("records")]
    out = pd.DataFrame(rows)
    out["_p"] = out["Priority"].map(_PRIORITY_ORDER)
    out["_f"] = pd.to_numeric(out["Core_Fit"], errors="coerce").fillna(-1)
    return (out.sort_values(["_p", "_f"], ascending=[True, False])
               .drop(columns=["_p", "_f"]).reset_index(drop=True))


# ──────────────────────────────────────────────
# CALIBRATION
# ──────────────────────────────────────────────

def calibrate(board: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Prediction error per estimate, from prospects whose real ratings
    were entered after the draft. Mean error > 0 means the rule reads
    low: add it to that rule's output (e.g. shift the speed chart)."""
    if board is None or board.empty:
        return pd.DataFrame()
    errs = {a: [] for a in PHYSICAL_ATTRS}
    for r in board.to_dict("records"):
        ev = evaluate_prospect(r, rules)
        for a in PHYSICAL_ATTRS:
            actual = _num(r.get(f"Actual_{a}"))
            if actual is not None and ev[a] is not None:
                errs[a].append(actual - ev[a])
    rows = []
    for a, e in errs.items():
        if not e:
            continue
        s = pd.Series(e, dtype=float)
        rows.append({
            "Rating": a, "Players": len(e),
            "Mean_Error": round(s.mean(), 1),
            "Avg_Miss": round(s.abs().mean(), 1),
            "Within_2": f"{(s.abs() <= 2).mean() * 100:.0f}%",
        })
    return pd.DataFrame(rows)
