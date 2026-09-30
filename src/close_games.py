"""
Close-game analysis: how the franchise plays in one-score games versus
games decided by more.

Close-game record is a standing metric for this franchise, and on the
shipped log the split is stark (4-9 in one-score games against 13-4
otherwise). This module answers "what's different in those games" from
the same prepared game log every other tab reads, so the Home panel and
the GM Chat quote identical numbers.

Every stat column is optional: the log comes from user uploads and
Google Sheets, so a missing column drops its row rather than raising.
"""

import pandas as pd

from src.game_log import efficiency_rates

CLOSE_MARGIN = 8  # one-score game
FG_MARGIN = 3     # decided by a field goal or less

# (column, label, higher_is_better). Per-game averages.
_STAT_ROWS = [
    ("Points_For", "Points scored", True),
    ("Points_Against", "Points allowed", False),
    ("Turnovers", "Turnovers", False),
    ("Takeaways", "Takeaways", True),
    ("Total_Yards", "Yards gained", True),
    ("Total_Yards_Allowed", "Yards allowed", False),
    ("Sacks_For", "Sacks", True),
    ("First_Downs", "First downs", True),
    ("RZ_TD_Made", "Red zone TDs", True),
]

# A gap has to be at least this large, relative to the decided-game
# value, before it's called out as a driver. Below that, 12 games can't
# tell it from noise.
_DRIVER_MIN_REL_GAP = 0.15
# Below this relative gap the two groups are shown as level.
NEUTRAL_REL_GAP = 0.05

_NOT_DRIVERS = {"Turnover margin", "Points scored", "Points allowed"}


def _margin(df: pd.DataFrame) -> "pd.Series | None":
    if "Score_Diff" in df.columns:
        return pd.to_numeric(df["Score_Diff"], errors="coerce")
    if "Points_For" in df.columns and "Points_Against" in df.columns:
        return (pd.to_numeric(df["Points_For"], errors="coerce")
                - pd.to_numeric(df["Points_Against"], errors="coerce"))
    return None


def record(df: pd.DataFrame) -> dict:
    wins = int((df["Result"] == "WIN").sum())
    losses = int((df["Result"] == "LOSS").sum())
    ties = int((df["Result"] == "TIE").sum())
    decided = wins + losses + ties
    return {
        "games": len(df), "wins": wins, "losses": losses, "ties": ties,
        "record": f"{wins}-{losses}" + (f"-{ties}" if ties else ""),
        # A tie counts as half a win, as the NFL computes win percentage.
        "win_pct": (wins + 0.5 * ties) / decided * 100 if decided else None,
    }


def _avg(df: pd.DataFrame, col: str) -> "float | None":
    if col not in df.columns or df.empty:
        return None
    v = pd.to_numeric(df[col], errors="coerce").mean()
    return None if pd.isna(v) else float(v)


def _group_stats(df: pd.DataFrame) -> dict:
    out = record(df)
    out["stats"] = {col: _avg(df, col) for col, _, _ in _STAT_ROWS}
    to, ta = out["stats"]["Turnovers"], out["stats"]["Takeaways"]
    out["turnover_margin"] = (ta - to) if to is not None and ta is not None else None
    eff = efficiency_rates(df)
    out["third_down_pct"] = eff["third_down_pct"]
    out["rz_td_pct"] = eff["rz_td_pct"]
    return out


def analyze(df: "pd.DataFrame | None", margin: int = CLOSE_MARGIN) -> "dict | None":
    """Split the log into close and decided games and compare them.

    Returns None when there's nothing to split (no log, no Result
    column, or no way to compute a margin). Otherwise:

        close / decided: record, win %, per-game stat averages,
                         turnover margin, 3rd down / RZ TD % if tracked
        fg:              record in games decided by <= 3
        one_score_4_8:   record in games decided by 4 to `margin`
        rows:            [{label, close, decided, higher_is_better}] for
                         stats present in both groups
        drivers:         rows where close games are worse by a margin
                         worth mentioning, biggest relative gap first
        games:           the close games, most recent last
    """
    if df is None or df.empty or "Result" not in df.columns:
        return None
    diff = _margin(df)
    if diff is None:
        return None

    close_mask = diff.abs() <= margin
    close, decided = df[close_mask], df[~close_mask & diff.notna()]
    fg = df[diff.abs() <= FG_MARGIN]
    mid = df[(diff.abs() > FG_MARGIN) & close_mask]

    c, d = _group_stats(close), _group_stats(decided)

    rows = []
    for col, label, higher_better in _STAT_ROWS:
        cv, dv = c["stats"][col], d["stats"][col]
        if cv is not None and dv is not None:
            rows.append({"label": label, "close": cv, "decided": dv,
                         "higher_is_better": higher_better})
    if c["turnover_margin"] is not None and d["turnover_margin"] is not None:
        rows.append({"label": "Turnover margin", "close": c["turnover_margin"],
                     "decided": d["turnover_margin"], "higher_is_better": True})

    drivers = []
    for r in rows:
        # Turnover margin restates the turnovers/takeaways rows, and
        # points are the outcome being explained (close games have
        # narrower scores by definition), not a cause.
        if r["label"] in _NOT_DRIVERS:
            continue
        gap = r["close"] - r["decided"]
        worse = gap < 0 if r["higher_is_better"] else gap > 0
        base = abs(r["decided"]) or 1.0
        rel = abs(gap) / base
        if worse and rel >= _DRIVER_MIN_REL_GAP:
            drivers.append({**r, "rel_gap": rel})
    drivers.sort(key=lambda r: r["rel_gap"], reverse=True)

    games = close.assign(_margin=diff[close_mask])
    return {
        "margin": margin,
        "close": c, "decided": d,
        "fg": record(fg), "one_score_4_8": record(mid),
        "rows": rows, "drivers": drivers,
        "games": games,
    }


def summary_lines(result: "dict | None") -> "list[str]":
    """Plain-text lines for the GM Chat context."""
    if not result or not result["close"]["games"]:
        return []
    c, d = result["close"], result["decided"]
    lines = [
        f"  Close games (<= {result['margin']} pts): {c['record']} "
        f"vs {d['record']} in games decided by more",
        f"    Decided by <= {FG_MARGIN}: {result['fg']['record']}; "
        f"by 4-{result['margin']}: {result['one_score_4_8']['record']}",
    ]
    for r in result["rows"]:
        lines.append(f"    {r['label']}/game: {r['close']:.2f} close vs "
                     f"{r['decided']:.2f} decided")
    return lines
