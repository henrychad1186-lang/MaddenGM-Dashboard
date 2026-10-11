"""
Scheme and playbook vocabulary, and the per-scheme comparison behind
"which of these is actually winning us games".

Four things are recorded per game, because a franchise runs two of each
and grading a whole side of the ball with one label cannot say which one
is the problem:

    offensive scheme    Playbook       (see the column note below)
    offensive playbook  Off_Playbook
    defensive scheme    Def_Scheme
    defensive playbook  Def_Playbook

## Why the offensive scheme lives in a column called `Playbook`

It is the column the log has always had, and the 42 games already on
file carry values that are plainly offensive schemes — "WestCoast Zone
Run", "Vertical Zone Run" — not playbooks. Renaming it would mean
rewriting every row of the user's CSV, the one operation `game_log`
exists to avoid, and would break every Google Sheet and uploaded file
pointed at this dashboard. So the name stays and `OFF_SCHEME` is how the
rest of the code refers to it.

## Why these lists are defaults, not rules

Every picker in the app accepts a value that isn't here
(`accept_new_options`), and `options()` always folds in whatever the log
already contains. Madden's exact in-game naming is not something this
module can verify, so being wrong about a label must cost the user a
typed correction, not a column they cannot fill. `normalize` is what
keeps that from fragmenting the data: it maps case and spacing variants
onto one canonical spelling, so a typed "west coast zone run" lands on
the same scheme as the 22 games already logged under "WestCoast Zone
Run" rather than starting a rival one-game scheme beside it.
"""

import pandas as pd

from src import close_games
from src.game_log import efficiency_rates

# ── Columns ───────────────────────────────────────────────────────────
OFF_SCHEME = "Playbook"          # legacy name; holds the offensive scheme
OFF_PLAYBOOK = "Off_Playbook"
DEF_SCHEME = "Def_Scheme"
DEF_PLAYBOOK = "Def_Playbook"

SCHEME_COLUMNS = [OFF_SCHEME, OFF_PLAYBOOK, DEF_SCHEME, DEF_PLAYBOOK]

# ── Vocabulary ────────────────────────────────────────────────────────
# Spelled as the shipped log spells them. Madden writes "West Coast";
# this franchise's 22 logged games write "WestCoast", and matching the
# data matters more than matching the menu — `normalize` accepts both.
PASS_SCHEMES = ["WestCoast", "Vertical", "Spread", "Run N Gun"]
RUN_SCHEMES = ["Zone Run", "Power Run"]

# The offensive scheme is a pass scheme and a run scheme together, which
# is how the existing rows read and how the form asks for it.
OFF_SCHEMES = [f"{p} {r}" for p in PASS_SCHEMES for r in RUN_SCHEMES]

DEF_SCHEMES = [
    "Base 4-3", "Base 3-4", "Multiple D", "Tampa 2", "46 Defense",
    "Nickel Heavy", "Dime Heavy",
]

_TEAM_PLAYBOOKS = [
    "Cardinals", "Falcons", "Ravens", "Bills", "Panthers", "Bears",
    "Bengals", "Browns", "Cowboys", "Broncos", "Lions", "Packers",
    "Texans", "Colts", "Jaguars", "Chiefs", "Chargers", "Rams",
    "Raiders", "Dolphins", "Vikings", "Patriots", "Saints", "Giants",
    "Jets", "Eagles", "Steelers", "Seahawks", "49ers", "Buccaneers",
    "Titans", "Commanders",
]

# Generic books first: a franchise running one is far likelier to be
# running it on purpose than to have picked it off a 32-long team list.
OFF_PLAYBOOKS = [
    "Balanced", "Pass Heavy", "Run Heavy", "Spread", "West Coast",
    "Vertical", "Run N Gun", "Pistol",
] + _TEAM_PLAYBOOKS

DEF_PLAYBOOKS = [
    "Balanced", "4-3", "3-4", "46", "Multiple D", "Nickel", "Dime",
] + _TEAM_PLAYBOOKS

DEFAULTS = {
    OFF_SCHEME: OFF_SCHEMES,
    OFF_PLAYBOOK: OFF_PLAYBOOKS,
    DEF_SCHEME: DEF_SCHEMES,
    DEF_PLAYBOOK: DEF_PLAYBOOKS,
}

LABELS = {
    OFF_SCHEME: "Offensive scheme",
    OFF_PLAYBOOK: "Offensive playbook",
    DEF_SCHEME: "Defensive scheme",
    DEF_PLAYBOOK: "Defensive playbook",
}

# Which side of the ball each dimension is responsible for. The Schemes
# tab ranks a defensive scheme on points and yards *allowed*; ranking it
# on PPG would credit it for the offense's work.
SIDES = {
    OFF_SCHEME: "offense",
    OFF_PLAYBOOK: "offense",
    DEF_SCHEME: "defense",
    DEF_PLAYBOOK: "defense",
}


def _clean(text) -> str:
    """Trim and collapse internal whitespace; "" for anything blank.

    A trailing space used to be enough to start a rival scheme that
    looked identical in the UI and split the comparison in two.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return " ".join(str(text).split())


def normalize(text, column: str = None, known=()) -> str:
    """Canonical spelling of one scheme/playbook value.

    Matches case-insensitively (and ignoring spacing) against the
    defaults for `column` plus any `known` values already in the log,
    returning the spelling those use. An unrecognised value is cleaned
    and kept as typed — the vocabulary is a default, not a whitelist.
    """
    cleaned = _clean(text)
    if not cleaned:
        return ""
    vocabulary = list(known) + list(DEFAULTS.get(column, []))
    folded = cleaned.casefold().replace(" ", "")
    for candidate in vocabulary:
        candidate = _clean(candidate)
        if candidate and candidate.casefold().replace(" ", "") == folded:
            return candidate
    return cleaned


def logged_values(df: pd.DataFrame, column: str) -> "list[str]":
    """Distinct non-blank values of `column` already in the log.

    Ordered most-recently-logged first, so the caller can offer the
    scheme this franchise is actually running before the 39 it isn't.
    """
    if df is None or df.empty or column not in df.columns:
        return []
    seen, out = set(), []
    for value in reversed(df[column].tolist()):
        value = _clean(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def options(df: pd.DataFrame, column: str) -> "list[str]":
    """Pick-list for `column`: what's been used, then the defaults.

    Used values lead because they are what this franchise actually
    runs; the defaults follow so a new scheme is one scroll away rather
    than something to spell from memory.
    """
    used = logged_values(df, column)
    folded = {v.casefold().replace(" ", "") for v in used}
    return used + [d for d in DEFAULTS.get(column, [])
                   if d.casefold().replace(" ", "") not in folded]


def current(df: pd.DataFrame, column: str) -> str:
    """What this franchise is running now — the most recent logged value.

    This is the entry form's prefill. It used to be `sorted(values)[-1]`,
    which reads as "the last one used" but is really the alphabetically
    last: a franchise that switched to "Air Raid" got "WestCoast Zone
    Run" prefilled every week after, and the mislabelled games it
    produced fed straight into the comparison below.
    """
    used = logged_values(df, column)
    return used[0] if used else ""


def split_off_scheme(text, known=()) -> "tuple[str, str]":
    """An offensive scheme as (pass scheme, run scheme).

    Tolerant of what is already on file: the run scheme is whichever
    known run scheme the string ends with, and everything before it is
    the pass scheme. A value matching neither comes back as
    (whole string, "") so the form can still show it.
    """
    cleaned = normalize(text, OFF_SCHEME, known)
    if not cleaned:
        return "", ""
    folded = cleaned.casefold().replace(" ", "")
    for run in RUN_SCHEMES:
        tail = run.casefold().replace(" ", "")
        if folded.endswith(tail) and len(folded) > len(tail):
            return _clean(cleaned[:len(cleaned) - len(run)]), run
    return cleaned, ""


def join_off_scheme(pass_scheme, run_scheme) -> str:
    """(pass, run) back into one stored value, either part optional."""
    return " ".join(p for p in (_clean(pass_scheme), _clean(run_scheme)) if p)


# ── Comparison ────────────────────────────────────────────────────────
# (key, label, higher_is_better, side). `side` is which of the two
# dimension kinds the row is evidence for; "both" rows show either way.
METRICS = [
    ("win_pct", "Win %", True, "both"),
    ("margin", "Avg margin", True, "both"),
    ("ppg", "PPG", True, "offense"),
    ("total_ypg", "Total YPG", True, "offense"),
    ("pass_ypg", "Pass YPG", True, "offense"),
    ("rush_ypg", "Rush YPG", True, "offense"),
    ("third_down_pct", "3rd down %", True, "offense"),
    ("rz_td_pct", "RZ TD %", True, "offense"),
    ("turnovers", "TO/G", False, "offense"),
    ("opp_ppg", "Opp PPG", False, "defense"),
    ("total_ypg_allowed", "Yds allowed/G", False, "defense"),
    ("sacks", "Sacks/G", True, "defense"),
    ("takeaways", "Takeaways/G", True, "defense"),
]

# Below this, a split is reported but not ranked on. Six games is the
# smaller arm of the shipped log, and a 2-game scheme out-margining a
# 22-game one by four points is noise, not a finding.
MIN_GAMES = 4


def _mean(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    value = pd.to_numeric(df[column], errors="coerce").mean()
    return None if pd.isna(value) else float(value)


def _margin(df: pd.DataFrame):
    if "Score_Diff" in df.columns:
        value = pd.to_numeric(df["Score_Diff"], errors="coerce").mean()
        return None if pd.isna(value) else float(value)
    pf, pa = _mean(df, "Points_For"), _mean(df, "Points_Against")
    return None if pf is None or pa is None else pf - pa


def stats_for(df: pd.DataFrame) -> dict:
    """Every comparison metric for one group of games."""
    rec = close_games.record(df) if "Result" in df.columns else {
        "record": "", "win_pct": None}
    rates = efficiency_rates(df)
    return {
        "games": len(df),
        "record": rec.get("record", ""),
        "win_pct": rec.get("win_pct"),
        "margin": _margin(df),
        "ppg": _mean(df, "Points_For"),
        "opp_ppg": _mean(df, "Points_Against"),
        "pass_ypg": _mean(df, "Pass_Yards"),
        "rush_ypg": _mean(df, "Rush_Yards"),
        "total_ypg": _mean(df, "Total_Yards"),
        "total_ypg_allowed": _mean(df, "Total_Yards_Allowed"),
        "turnovers": _mean(df, "Turnovers"),
        "takeaways": _mean(df, "Takeaways"),
        "sacks": _mean(df, "Sacks_For"),
        "third_down_pct": rates.get("third_down_pct"),
        "rz_td_pct": rates.get("rz_td_pct"),
    }


def compare(df: pd.DataFrame, column: str) -> "list[dict]":
    """Per-value stats for `column`, best first.

    Ranked on average point margin rather than win %. Win % is what the
    user is after, but over six games it moves in 16-point steps and a
    single one-score game reorders the table; margin uses every point of
    every game and says the same thing with far less noise. Win % is
    still reported, and `ranked` marks the groups too small to trust.

    Games with the column blank are left out — "not recorded" is not a
    scheme, and bundling 14 unlabelled games into one row would make it
    the biggest "scheme" in the comparison.
    """
    if df is None or df.empty or column not in df.columns:
        return []
    labelled = df[df[column].map(lambda v: bool(_clean(v)))]
    if labelled.empty:
        return []
    rows = []
    for value in logged_values(labelled, column):
        group = labelled[labelled[column].map(_clean) == value]
        rows.append({"value": value, "ranked": len(group) >= MIN_GAMES,
                     **stats_for(group)})
    rows.sort(key=lambda r: (r["ranked"],
                             r["margin"] if r["margin"] is not None else -999),
              reverse=True)
    return rows


def metrics_for(column: str) -> "list[tuple]":
    """The METRICS rows worth showing for this dimension's side."""
    side = SIDES.get(column, "offense")
    return [m for m in METRICS if m[3] in ("both", side)]


def verdict(rows: "list[dict]", column: str) -> str:
    """One sentence on what the comparison supports. "" if it supports nothing.

    Deliberately refuses to crown a winner on thin evidence: the whole
    point of recording this is to beat a hunch, and a confident sentence
    off two games is worse than no sentence.
    """
    label = LABELS.get(column, "scheme").lower()
    ranked = [r for r in rows if r["ranked"]]
    if not rows:
        return ""
    if len(rows) == 1:
        only = rows[0]
        return (f"Only one {label} on file — **{only['value']}**, "
                f"{only['record']} over {only['games']} games. "
                f"Log a game under another one to get a comparison.")
    if len(ranked) < 2:
        return (f"No {label} has {MIN_GAMES} games yet, so nothing here is "
                f"worth acting on. {len(rows)} are on file; keep logging.")
    best, rest = ranked[0], ranked[1]
    gap = (best["margin"] or 0) - (rest["margin"] or 0)
    better = (f"**{best['value']}** is ahead on margin "
              f"({best['margin']:+.1f} vs {rest['margin']:+.1f} per game) "
              f"over {best['games']} games to {rest['games']}.")
    if gap < 3:
        return (better + " That gap is small enough that it could still be "
                "the schedule rather than the scheme.")
    return better + (f" At {gap:.1f} points a game that is a real "
                     f"difference, not a rounding one.")
