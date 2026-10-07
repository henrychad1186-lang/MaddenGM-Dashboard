"""
Consistency checks on the game log.

The log is hand-entered from Madden box scores (CSV, upload or Google
Sheet), and the entry mistakes are systematic enough to catch by rule:
Madden's "Total Yards Gained" row counts return yards, so copying it in
breaks total = pass + rush; time of possession copied as a template
increments by exactly a minute a game. Every check reads only columns
that are present, so a partial log gets the checks it can support.

Nothing here edits data. The checks point at rows to verify against the
box score; which of the disagreeing numbers is wrong is for the person
holding the box score to decide.
"""

import pandas as pd

# Madden's default quarter is 11 minutes (44-minute game). A side
# holding the ball under a quarter of that (or over three quarters)
# is implausible enough to verify.
DEFAULT_GAME_MINUTES = 44
_TOP_LOW_SHARE, _TOP_HIGH_SHARE = 0.25, 0.75
# This many consecutive games whose TOP rises by exactly one minute
# looks like a template, not real data.
_PLACEHOLDER_RUN = 3
# A total this far above pass + rush points at copied return yards.
_RETURN_GAP = 10

_SUM_CHECKS = [
    ("Total_Yards", ("Pass_Yards", "Rush_Yards"), "Offense"),
    ("Total_Yards_Allowed", ("Pass_Yards_Allowed", "Rush_Yards_Allowed"), "Defense"),
]


_RATE_CHECKS = [
    ("Third_Down_Conv", "Third_Down_Att", "3rd-down conversions"),
    ("RZ_TD_Made", "RZ_Att", "Red zone TDs"),
]


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def _game(df: pd.DataFrame, i) -> str:
    if "GAME_ID" in df.columns and pd.notna(df.at[i, "GAME_ID"]):
        v = df.at[i, "GAME_ID"]
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    return f"row {i + 1}"


def _opp(df: pd.DataFrame, i) -> str:
    return str(df.at[i, "Opponent"]) if "Opponent" in df.columns else ""


def top_minutes(value) -> "float | None":
    """'MM:SS' -> minutes, or None if it isn't one."""
    if not isinstance(value, str) or ":" not in value:
        return None
    mm, _, ss = value.strip().partition(":")
    try:
        m, s = int(mm), int(ss)
    except ValueError:
        return None
    return m + s / 60 if 0 <= s < 60 and m >= 0 else None


def check_log(df: "pd.DataFrame | None",
              game_minutes: int = DEFAULT_GAME_MINUTES) -> "list[dict]":
    """Issues found in the log: [{game, opponent, check, detail}], in
    log order within each check."""
    if df is None or df.empty:
        return []
    df = df.reset_index(drop=True)
    issues = []

    def add(i, check, detail):
        issues.append({"game": _game(df, i), "opponent": _opp(df, i),
                       "check": check, "detail": detail})

    for total, (a, b), side in _SUM_CHECKS:
        if not {total, a, b} <= set(df.columns):
            continue
        t, x, y = _num(df, total), _num(df, a), _num(df, b)
        for i in df.index:
            if pd.isna(x[i]) or pd.isna(y[i]):
                continue
            if pd.isna(t[i]):
                add(i, f"{side} total yards missing",
                    f"{a} + {b} = {x[i] + y[i]:.0f}; {total} is blank")
            elif t[i] != x[i] + y[i]:
                gap = t[i] - (x[i] + y[i])
                # Return yards are rarely under 10; a smaller gap is more
                # likely a typo in one of the three numbers.
                hint = (" (likely Madden's 'Total Yards Gained', which "
                        "includes return yards)") if gap >= _RETURN_GAP else ""
                add(i, f"{side} yards don't add up",
                    f"{total} {t[i]:.0f} vs pass {x[i]:.0f} + rush {y[i]:.0f} "
                    f"= {x[i] + y[i]:.0f} ({gap:+.0f}){hint}")

    # Made can't exceed attempted. The entry form enforces this, but rows
    # from a CSV or a Sheet never pass through the form, and one bad row
    # skews the 3rd-down / red-zone rates on the KPI row and in the chat.
    for made, att, label in _RATE_CHECKS:
        if not {made, att} <= set(df.columns):
            continue
        m, a = _num(df, made), _num(df, att)
        for i in df.index:
            if pd.notna(m[i]) and pd.notna(a[i]) and m[i] > a[i]:
                add(i, f"{label} exceed attempts",
                    f"{made} {m[i]:.0f} > {att} {a[i]:.0f}")

    if {"Points_For", "Points_Against"} <= set(df.columns):
        pf, pa = _num(df, "Points_For"), _num(df, "Points_Against")
        if "Point_Differential" in df.columns:
            pdiff = _num(df, "Point_Differential")
            for i in df.index:
                if pd.notna(pdiff[i]) and pd.notna(pf[i]) and pd.notna(pa[i]) \
                        and pdiff[i] != pf[i] - pa[i]:
                    add(i, "Point differential wrong",
                        f"{pdiff[i]:+.0f} recorded, score {pf[i]:.0f}-{pa[i]:.0f} "
                        f"is {pf[i] - pa[i]:+.0f}")
        if "Result" in df.columns:
            res = df["Result"].astype(str).str.strip().str.upper().str[0]
            for i in df.index:
                if pd.isna(pf[i]) or pd.isna(pa[i]) or res[i] not in ("W", "L", "T"):
                    continue
                want = "W" if pf[i] > pa[i] else "L" if pf[i] < pa[i] else "T"
                if res[i] != want:
                    add(i, "Result doesn't match score",
                        f"{df.at[i, 'Result']} recorded, score {pf[i]:.0f}-{pa[i]:.0f}")

    if "TOP" in df.columns:
        # A list, not a Series: Series.apply turns the None for a blank
        # or unparseable cell into NaN, which passes `is not None` and
        # fails every range comparison, flagging blanks as implausible.
        mins = [top_minutes(v) for v in df["TOP"]]
        lo, hi = game_minutes * _TOP_LOW_SHARE, game_minutes * _TOP_HIGH_SHARE
        for i in df.index:
            m = mins[i]
            if m is not None and not lo <= m <= hi:
                add(i, "Time of possession implausible",
                    f"{df.at[i, 'TOP']} in a {game_minutes}-minute game "
                    f"(expected {int(lo)}:00-{int(hi)}:00)")
        # Runs of exactly +1:00 per game.
        run = [0]
        for i in range(1, len(df)):
            a, b = mins[i - 1], mins[i]
            if a is not None and b is not None and abs(b - a - 1) < 1e-9:
                run.append(i)
                continue
            if len(run) >= _PLACEHOLDER_RUN:
                _flag_run(df, run, add)
            run = [i]
        if len(run) >= _PLACEHOLDER_RUN:
            _flag_run(df, run, add)
    return issues


def _flag_run(df, run, add):
    first, last = df.at[run[0], "TOP"], df.at[run[-1], "TOP"]
    for i in run:
        add(i, "Time of possession looks like a placeholder",
            f"{len(run)} games in a row go up by exactly 1:00 "
            f"({first} to {last})")


def summary(issues: "list[dict]") -> "dict[str, int]":
    """Issue count per check, in first-seen order."""
    out: "dict[str, int]" = {}
    for it in issues:
        out[it["check"]] = out.get(it["check"], 0) + 1
    return out
