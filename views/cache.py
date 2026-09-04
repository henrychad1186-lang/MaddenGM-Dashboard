"""
Cached front door to the engines in `src/`.

Streamlit reruns the whole script on every widget interaction, and every
tab body runs on every rerun whether or not it's the visible one. Without
this layer that means `analyze_roster` runs twice per click (Franchise
Home and Roster Explorer both call it), `get_cap_summary` twice,
`positional_needs` twice, and `get_trade_value` sweeps the full roster
twice more for the leaderboard and the awards row — all recomputing
identical results from data that cannot change inside a single rerun.

The engines themselves stay Streamlit-free so they remain importable and
testable without a runtime; the caching lives here, at the boundary.

Cache keys always include `extra_players`. `st.cache_data` is shared
across every browser session in the process, so leaving the session's AI
GM additions out of the key would serve one visitor's roster to another.
Passing the list by value means a mutation (adding or removing a player)
lands on a different key and recomputes, which is exactly the invalidation
we want.
"""

import pandas as pd
import streamlit as st

from src import ai_gm, analytics
from src.roster import (
    get_cap_summary,
    get_position_grades,
    get_roster,
    get_team_summary,
)
from src.roster_analyzer import analyze_roster
from src.trade_engine import find_trade_partners

# Roster reads are keyed on (team, group, session extras). A handful of
# tabs and a couple of position-group selections cover the realistic key
# space; the bound just stops a long session from growing without limit.
_MAX_ENTRIES = 64


# ──────────────────────────────────────────────
# ROSTER READS
# ──────────────────────────────────────────────

@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_roster(team: str, group: str, extra_players: "list[dict] | None") -> pd.DataFrame:
    return get_roster(team, group, extra_players)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_team_summary(team: str, extra_players: "list[dict] | None") -> dict:
    return get_team_summary(team, extra_players)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_position_grades(team: str, extra_players: "list[dict] | None") -> "list[dict]":
    return get_position_grades(team, extra_players)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_cap_summary(team: str, extra_players: "list[dict] | None") -> dict:
    return get_cap_summary(team, extra_players)


# ──────────────────────────────────────────────
# DERIVED ANALYSIS — the expensive ones
# ──────────────────────────────────────────────

@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_roster_verdicts(team: str, extra_players: "list[dict] | None") -> "list[dict]":
    """Cut/keep verdicts. Walks the roster calling get_trade_value per player."""
    return analyze_roster(team, extra_players)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_positional_needs(team: str, extra_players: "list[dict] | None") -> "list[dict]":
    return ai_gm.positional_needs(team, extra_players)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_trade_value_table(team: str, extra_players: "list[dict] | None") -> pd.DataFrame:
    return analytics.build_trade_value_table(get_roster(team, "All", extra_players))


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_season_awards(team: str, extra_players: "list[dict] | None") -> "list[dict]":
    return analytics.select_season_awards(get_roster(team, "All", extra_players))


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_trade_partners(player: dict, user_team: str) -> "list[dict]":
    return find_trade_partners(player, user_team=user_team)


# ──────────────────────────────────────────────
# GAME-LOG ANALYTICS
# ──────────────────────────────────────────────
# DataFrame arguments hash by content, so these recompute exactly when the
# sidebar filters change the frame and not otherwise.

@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_scheme_stats(df: pd.DataFrame) -> "dict[str, dict]":
    return analytics.compute_scheme_stats(df)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_momentum(df: pd.DataFrame) -> pd.DataFrame:
    return analytics.compute_momentum(df)


@st.cache_data(show_spinner=False, max_entries=_MAX_ENTRIES)
def cached_coach_dna(df: pd.DataFrame) -> "dict | None":
    return analytics.compute_coach_dna(df)
