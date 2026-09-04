"""
Pure analytics behind the dashboard tabs — no Streamlit, no rendering.

Everything here used to live inline inside `app.py`'s `with tabs[n]:`
blocks, which meant it could only run inside a live Streamlit session and
could never be tested. The tab bodies in `views/` now call these functions
and do nothing but draw the result, so the arithmetic that decides an
award, a coaching archetype, or a momentum curve is verifiable on its own.

Every function takes plain DataFrames/dicts and returns plain
DataFrames/dicts, so they're safe to wrap in `@st.cache_data` from the
view layer (see `views/cache.py`).
"""

import pandas as pd

from src.trade_engine import _parse_salary, get_trade_value

# Positions counted as defenders when picking a Defensive Player of the Year.
DEFENSIVE_POSITIONS = ["EDGE", "DT", "MLB", "OLB", "CB", "FS", "SS"]

# Metrics compared side-by-side in the scheme head-to-head bar chart.
SCHEME_COMPARE_METRICS = ["PPG", "Opp PPG", "Pass YPG", "Rush YPG", "Total YPG"]


def _mean(df: pd.DataFrame, col: str, digits: int = 1) -> float:
    """Rounded column mean, or 0 when the column isn't in the data."""
    if col not in df.columns or df.empty:
        return 0
    value = df[col].mean()
    if pd.isna(value):
        return 0
    return round(value, digits)


# ──────────────────────────────────────────────
# SCHEME PERFORMANCE
# ──────────────────────────────────────────────

def compute_scheme_stats(df: pd.DataFrame) -> "dict[str, dict]":
    """Per-playbook record and per-game averages, keyed by scheme name.

    Returns {} when the log has no Playbook column, so the caller can skip
    the whole head-to-head section without a second column check.
    """
    if "Playbook" not in df.columns:
        return {}

    stats = {}
    for scheme in df["Playbook"].dropna().unique().tolist():
        s_df = df[df["Playbook"] == scheme]
        wins = int((s_df["Result"] == "WIN").sum()) if "Result" in s_df.columns else 0
        losses = len(s_df) - wins
        stats[scheme] = {
            "Games": len(s_df),
            "Record": f"{wins}-{losses}",
            "Win%": round(wins / max(len(s_df), 1) * 100, 1),
            "PPG": _mean(s_df, "Points_For"),
            "Opp PPG": _mean(s_df, "Points_Against"),
            "Pass YPG": _mean(s_df, "Pass_Yards"),
            "Rush YPG": _mean(s_df, "Rush_Yards"),
            "Total YPG": _mean(s_df, "Total_Yards"),
            "TO/G": _mean(s_df, "Turnovers", 2),
            "Takeaways/G": _mean(s_df, "Takeaways", 2),
            "Sacks/G": _mean(s_df, "Sacks_For"),
            "Avg Margin": _mean(s_df, "Score_Diff"),
        }
    return stats


def build_scheme_comparison(scheme_stats: "dict[str, dict]") -> pd.DataFrame:
    """Long-form (Scheme, Metric, Value) frame for the grouped bar chart."""
    rows = [
        {"Scheme": scheme, "Metric": metric, "Value": values[metric]}
        for scheme, values in scheme_stats.items()
        for metric in SCHEME_COMPARE_METRICS
    ]
    return pd.DataFrame(rows)


def compute_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Running win rate and rolling point margin, one row per game played."""
    momentum = df.copy().reset_index(drop=True)
    momentum["Game_Num"] = range(1, len(momentum) + 1)
    momentum["Win"] = (momentum["Result"] == "WIN").astype(int)
    momentum["Cum_Wins"] = momentum["Win"].cumsum()
    momentum["Win_Pct"] = (
        momentum["Cum_Wins"] / momentum["Game_Num"] * 100
    ).round(1)
    if "Score_Diff" in momentum.columns:
        momentum["Rolling_Margin"] = (
            momentum["Score_Diff"].rolling(3, min_periods=1).mean().round(1)
        )
    return momentum


def longest_win_streak(wins) -> int:
    """Longest run of consecutive wins in a sequence of 1/0 (or True/False)."""
    best = current = 0
    for won in wins:
        current = current + 1 if won else 0
        best = max(best, current)
    return best


# ──────────────────────────────────────────────
# COACH DNA
# ──────────────────────────────────────────────

def compute_coach_dna(df: pd.DataFrame, min_games: int = 3) -> "dict | None":
    """Coaching archetype plus the five 0-100 radar axes behind it.

    Returns None when the game log lacks the pass/rush/result columns or
    has fewer than `min_games` rows — the caller shows a prompt instead of
    a chart built on one game.
    """
    required = {"Pass_Yards", "Rush_Yards", "Result"}
    if not required.issubset(df.columns) or len(df) < min_games:
        return None

    total_pass = df["Pass_Yards"].sum()
    total_rush = df["Rush_Yards"].sum()
    pass_pct = total_pass / max(total_pass + total_rush, 1) * 100
    rush_pct = 100 - pass_pct

    win_pct = (df["Result"] == "WIN").sum() / len(df) * 100
    avg_pf = df["Points_For"].mean() if "Points_For" in df.columns else 0
    avg_to = df["Turnovers"].mean() if "Turnovers" in df.columns else 0
    avg_takeaways = df["Takeaways"].mean() if "Takeaways" in df.columns else 0
    avg_sacks = df["Sacks_For"].mean() if "Sacks_For" in df.columns else 0

    # 0-100 radar axes. The scaling constants are calibrated so a typical
    # good franchise lands mid-chart: 45 PPG maxes aggression, 2.5
    # turnovers/game zeroes out ball security.
    passing = min(pass_pct * 1.2, 100)
    rushing = min(rush_pct * 1.5, 100)
    aggression = min(avg_pf / 0.45, 100)
    ball_security = max(0, 100 - avg_to * 40)
    def_intensity = min(avg_sacks * 15 + avg_takeaways * 20, 100)

    if pass_pct > 60 and aggression > 65:
        archetype = "🌩️ Aggressive Air Raid"
    elif rush_pct > 45 and ball_security > 70:
        archetype = "🗿 Conservative Ground & Pound"
    elif pass_pct > 55 and ball_security > 60:
        archetype = "🎯 West Coast Tactician"
    elif def_intensity > 70:
        archetype = "🛡️ Defensive Mastermind"
    elif aggression > 70 and ball_security < 50:
        archetype = "🎰 Gunslinger Gambler"
    else:
        archetype = "⚖️ Balanced Strategist"

    return {
        "archetype": archetype,
        "pass_pct": pass_pct,
        "rush_pct": rush_pct,
        "win_pct": win_pct,
        "avg_pf": avg_pf,
        "avg_to": avg_to,
        "avg_takeaways": avg_takeaways,
        "avg_sacks": avg_sacks,
        "axes": {
            "Passing": passing,
            "Rushing": rushing,
            "Aggression": aggression,
            "Ball Security": ball_security,
            "Def Intensity": def_intensity,
        },
    }


# ──────────────────────────────────────────────
# TRADE VALUE LEADERBOARD
# ──────────────────────────────────────────────

def build_trade_value_table(roster_df: pd.DataFrame) -> pd.DataFrame:
    """Roster ranked by trade value, indexed 1..N under a "Rank" index."""
    if roster_df.empty:
        return pd.DataFrame(
            columns=["Name", "Pos", "OVR", "Age", "Dev", "Trade Value"])

    rows = []
    for _, player in roster_df.iterrows():
        rows.append({
            "Name": player["Name"],
            "Pos": player["Pos"],
            "OVR": int(player["OVR"]),
            "Age": int(player["Age"]),
            "Dev": player.get("Dev", "Normal"),
            "Trade Value": get_trade_value(player.to_dict()),
        })

    table = (
        pd.DataFrame(rows)
        .sort_values("Trade Value", ascending=False)
        .reset_index(drop=True)
    )
    table.index += 1
    table.index.name = "Rank"
    return table


# ──────────────────────────────────────────────
# SEASON AWARDS
# ──────────────────────────────────────────────

def _best_by(df: pd.DataFrame, column: str) -> "dict | None":
    """Row with the highest value in `column`, as a dict (None if empty)."""
    if df.empty:
        return None
    return df.loc[df[column].idxmax()].to_dict()


def select_season_awards(roster_df: pd.DataFrame) -> "list[dict]":
    """Pick MVP / DPOY / ROY / Iron Man / Best Contract from a roster.

    Always returns all five entries in a fixed order so the UI renders a
    stable row of cards; an award with no eligible player carries
    ``player=None`` and is drawn as an empty slot.
    """
    awards_spec = [
        ("🏆 MVP", "#FFD700", "Highest trade value on the roster"),
        ("🛡️ DPOY", "#6366f1", "Highest-rated defensive player"),
        ("⭐ ROY", "#10b981", "Best player age 22 or under"),
        ("💪 Iron Man", "#f59e0b", "Oldest player above 80 OVR"),
        ("💰 Best Contract", "#06b6d4", "Best OVR-to-cap ratio"),
    ]

    if roster_df.empty:
        return [
            {"title": title, "color": color, "desc": desc, "player": None}
            for title, color, desc in awards_spec
        ]

    scored = roster_df.copy()
    scored["TV"] = [get_trade_value(p) for p in roster_df.to_dict("records")]

    mvp = _best_by(scored, "TV")
    dpoy = _best_by(scored[scored["Pos"].isin(DEFENSIVE_POSITIONS)], "OVR")
    roy = _best_by(scored[scored["Age"] <= 22], "OVR")
    iron = _best_by(scored[(scored["Age"] >= 29) & (scored["OVR"] >= 80)], "Age")

    # Dead-cap figures are strings like "$600K"; parse them with the same
    # helper the trade engine uses so a sub-$1M hit isn't read as $600M and
    # scored as the worst contract on the roster instead of nearly the best.
    scored["_pen"] = [
        _parse_salary(p) for p in scored.get("Penalty", pd.Series([0] * len(scored)))
    ]
    with_penalty = scored[scored["_pen"] > 0].copy()
    if with_penalty.empty:
        best_contract = None
    else:
        with_penalty["value_ratio"] = (
            with_penalty["OVR"] / with_penalty["_pen"].clip(lower=0.1)
        )
        best_contract = _best_by(with_penalty, "value_ratio")

    players = [mvp, dpoy, roy, iron, best_contract]
    return [
        {"title": title, "color": color, "desc": desc, "player": player}
        for (title, color, desc), player in zip(awards_spec, players)
    ]


# ──────────────────────────────────────────────
# FRANCHISE HOME
# ──────────────────────────────────────────────

def top_needs(needs: "list[dict]", limit: int = 3) -> "list[dict]":
    """Unmet positional needs, most urgent first (Critical, then worst OVR)."""
    unmet = [n for n in needs if n["level"] != "Set"]
    unmet.sort(key=lambda n: (n["level"] != "Critical", n["avg_ovr"]))
    return unmet[:limit]


def actionable_moves(verdicts: "list[dict]", limit: int = 3) -> "list[dict]":
    """Players the cut/keep analyzer flagged as anything other than KEEP.

    `verdicts` arrives already sorted CUT → TRADE → KEEP by trade value,
    so taking the head preserves that ordering.
    """
    return [v for v in verdicts if v["Verdict"] != "KEEP"][:limit]


def record_from_log(df: pd.DataFrame) -> "tuple[int, int]":
    """(wins, losses) from a game log; (0, 0) when there's no Result column."""
    if "Result" not in df.columns:
        return 0, 0
    return int((df["Result"] == "WIN").sum()), int((df["Result"] == "LOSS").sum())
