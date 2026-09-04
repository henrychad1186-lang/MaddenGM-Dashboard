"""
Madden 27 GM War Room — Streamlit entry point.

This file does three things and nothing else: configure the page, gather
the per-rerun state into an `AppContext`, and hand that context to each
tab. Every tab's rendering lives in its own module under `views/`, and the
analysis behind them lives in `src/` where it can be tested without a
Streamlit runtime.
"""

import pandas as pd
import streamlit as st

from src.trade_engine import DEMO_ROSTERS as TRADE_ROSTERS
from views import (
    ai_gm_tab,
    awards,
    coach_dna,
    dynasty_tab,
    home,
    progression_tab,
    raw_data,
    roster_explorer,
    scheme,
    sidebar,
    theme,
    trade,
    wear_tear,
)
from views.context import AppContext

st.set_page_config(
    page_title="Madden 27 GM War Room",
    layout="wide",
    page_icon="🏈",
)

theme.inject_css()
theme.render_hero()

# ── PER-RERUN STATE ──
game_log, my_team = sidebar.render()

# Players added via the AI GM Assistant tab live only in this browser
# session's state, never in the shared roster/trade_engine module globals,
# so one visitor's additions never leak into another visitor's view.
if "ai_gm_players" not in st.session_state:
    st.session_state.ai_gm_players = []
extra_players = st.session_state.ai_gm_players

if extra_players:
    # Keep _id (unlike the roster/cap paths, which never expose it to the
    # UI) — the Trade Machine selects players by Name, and _id is the only
    # thing that could disambiguate same-named players there later. It's
    # an inert extra column for get_trade_value() and the CPU-side rows.
    effective_trade_rosters = pd.concat(
        [TRADE_ROSTERS, pd.DataFrame(extra_players)], ignore_index=True)
else:
    effective_trade_rosters = TRADE_ROSTERS

ctx = AppContext(
    df=game_log,
    my_team=my_team,
    extra_players=extra_players,
    trade_rosters=TRADE_ROSTERS,
    effective_trade_rosters=effective_trade_rosters,
)

# ── ABOVE THE FOLD ──
home.render_empty_data_guard(ctx)
home.render(ctx)

# ── TABS ──
TABS = [
    ("📊 Scheme Performance", scheme.render),
    ("💪 Wear & Tear", wear_tear.render),
    ("🏈 Trade Machine", trade.render),
    ("🏛️ Dynasty", dynasty_tab.render),
    ("📋 Roster Explorer", roster_explorer.render),
    ("🏆 Season Awards", awards.render),
    ("🎯 Coach DNA", coach_dna.render),
    ("📈 Progression", progression_tab.render),
    ("🗂️ Raw Data", raw_data.render),
    ("🤖 AI GM Assistant", ai_gm_tab.render),
]

for tab, (_label, render_tab) in zip(st.tabs([label for label, _ in TABS]), TABS):
    with tab:
        render_tab(ctx)
