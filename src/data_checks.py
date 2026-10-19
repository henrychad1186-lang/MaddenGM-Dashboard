"""
Consistency checks on the game log.

The log is hand-entered from Madden box scores (CSV, upload or Google
Sheet), and the entry mistakes are systematic enough to catch by rule:
Madden's "Total Yards Gained" row counts return yards, so copying it in
breaks total = pass + rush; time of possession copied as a template
increments by exactly a minute a game. Every check reads only columns
that are present, so a partial log gets the checks it can support.

Several of these guard a rule the entry form already enforces, because
a row pasted from a CSV or synced from a Google Sheet never passes
through the form — made-above-attempted and season/week placement are
both here for that reason.

Nothing here edits data. The checks point at rows to verify against the
box score; which of the disagreeing numbers is wrong is for the person
holding the box score to decide.
"""

import pandas as pd

from src.game_log import parse_top
from src.season import SEASON_MAX, SEASON_MIN, WEEK_MAX, WEEK_MIN

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


# Made, attempted, what the made column counts, and what the attempted
# column is called in the entry form — the form says "red zone trips",
# so the check says trips too rather than inventing a second name for
# the same number.
_RATE_CHECKS = [
    ("Third_Down_Conv", "Third_Down_Att", "3rd-down conversions", "attempts"),
    ("RZ_TD_Made", "RZ_Att", "Red zone TDs", "trips"),
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


def check_log(df: "pd.DataFrame | None",
              game_minutes: int = DEFAULT_GAME_MINUTES) -> "list[dict]":
    """Issues found in the log: [{game, opponent, check, detail}], in
    log order within each check.

    One function per family of check, run in a fixed order so the panel
    groups the way the reader expects. Each takes the whole frame and
    the `add` callback, and each is responsible for skipping itself when
    the columns it reads are absent — a partial log gets the checks it
    can support.
    """
    if df is None or df.empty:
        return []
    df = df.reset_index(drop=True)
    issues = []

    def add(i, check, detail):
        issues.append({"game": _game(df, i), "opponent": _opp(df, i),
                       "check": check, "detail": detail})

    _check_sums(df, add)
    _check_rates(df, add)
    _check_scoring(df, add)
    _check_placement(df, add)
    _check_time_of_possession(df, add, game_minutes)
    return issues


def _check_sums(df, add):
    """Total yards against its pass and rush components."""
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


def _check_rates(df, add):
    """Made can't exceed attempted.

    The entry form enforces this, but rows from a CSV or a Sheet never
    pass through the form, and one bad row skews the 3rd-down /
    red-zone rates on the KPI row and in the chat.

    Only rows with attempts above zero can do that skewing:
    `game_log._rate` filters on `a > 0`, so a zero-attempt row never
    reaches the rates. Zero also means "not tracked" everywhere else —
    the form writes `int(td_att) if td_att else ""` and
    `efficiency_rates` carries a `(conv == 0) & (att == 0)` sentinel —
    and a spreadsheet exporting an untracked cell as 0 rather than
    blank is the ordinary case on exactly this input path. Flagging it
    would send the user to the box score over a number nothing reads.
    """
    for made, att, label, denom in _RATE_CHECKS:
        if not {made, att} <= set(df.columns):
            continue
        m, a = _num(df, made), _num(df, att)
        for i in df.index:
            if pd.notna(m[i]) and pd.notna(a[i]) and a[i] > 0 and m[i] > a[i]:
                add(i, f"{label} exceed {denom}",
                    f"{made} {m[i]:.0f} > {att} {a[i]:.0f}")


def _check_scoring(df, add):
    """Point differential and W/L/T against the score they describe."""
    if not {"Points_For", "Points_Against"} <= set(df.columns):
        return
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


def _check_time_of_possession(df, add, game_minutes):
    """TOP against a plausible share of the game, and against itself."""
    if "TOP" not in df.columns:
        return
    # A list, not a Series: Series.apply turns the None for a blank
    # or unparseable cell into NaN, which passes `is not None` and
    # fails every range comparison, flagging blanks as implausible.
    mins = [parse_top(v) for v in df["TOP"]]
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


def _check_placement(df, add):
    """Where each game sits in the franchise timeline.

    `game_log.assign_season_week` already refuses an out-of-range slot,
    a double-booked week and a half-filled placement on the way in. A
    row pasted from a CSV or synced from a Google Sheet never reaches
    it, so until now nothing read Season or Week at all — the same gap
    `_check_rates` exists to close for made-above-attempted.

    What is deliberately *not* flagged: a game with neither a season nor
    a week. Every shipped row is in exactly that state, which makes it
    the ordinary case rather than a mistake, and the season/week form
    (fed by `game_log.games_missing_season_week`) is what fills it in.
    An unplaced game is incomplete, not contradictory, and reporting it
    here would bury the real findings under one item per game.
    """
    if not {"Season", "Week"} <= set(df.columns):
        return
    season, week = _num(df, "Season"), _num(df, "Week")
    seen: "dict[tuple, str]" = {}
    for i in df.index:
        s, w = season[i], week[i]
        if pd.isna(s) and pd.isna(w):
            continue
        if pd.isna(s) or pd.isna(w):
            _flag_half_placed(df, i, s, w, add)
            continue
        _flag_out_of_range(i, s, w, add)
        slot = (s, w)
        if slot in seen:
            # Worded as `game_log._week_already_taken` words it, so the
            # checker and the entry form describe one problem one way.
            add(i, "Two games in the same week",
                f"Game #{seen[slot]} is already season {s:.0f} week {w:.0f}")
        else:
            seen[slot] = _game(df, i)


def _flag_half_placed(df, i, season, week, add):
    """One half of a placement with nothing to pair it to.

    A week with no season cannot be ordered against any other game, and
    a season with no week leaves `duplicate_week` nothing to collide
    with — so half a placement buys none of what a placement is for.
    """
    if pd.isna(week):
        add(i, "Game has a season but no week",
            f"Season {season:.0f} recorded, Week is {_unreadable(df, i, 'Week')}")
    else:
        add(i, "Game has a week but no season",
            f"Week {week:.0f} recorded, Season is "
            f"{_unreadable(df, i, 'Season')}")


def _flag_out_of_range(i, season, week, add):
    if not SEASON_MIN <= season <= SEASON_MAX:
        add(i, "Season out of range",
            f"{season:.0f} recorded; the franchise runs "
            f"{SEASON_MIN}-{SEASON_MAX}")
    if not WEEK_MIN <= week <= WEEK_MAX:
        add(i, "Week out of range",
            f"{week:.0f} recorded; a season runs weeks "
            f"{WEEK_MIN}-{WEEK_MAX} including the playoffs")


def _unreadable(df, i, column) -> str:
    """Why a cell did not parse — blank, or holding something it can't use.

    Saying "blank" about a cell with `wk3` in it sends the reader to
    look for an empty box they will not find.
    """
    raw = df.at[i, column]
    text = "" if raw is None or pd.isna(raw) else str(raw).strip()
    return "blank" if not text else f"{text!r}, which is not a number"


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
