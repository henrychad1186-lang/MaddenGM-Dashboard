"""
Above-the-fold summary: the KPI row and the Franchise Home cards.

Franchise Home pulls from the same functions the tabs use — cap summary,
positional needs, cut/keep verdicts — just surfaced up front so the most
actionable state doesn't require a tour of all ten tabs.
"""

import streamlit as st

from src import analytics
from views import theme
from views.cache import (
    cached_cap_summary,
    cached_positional_needs,
    cached_roster_verdicts,
)
from views.context import AppContext

_VERDICT_COLORS = {"CUT": "#ff5252", "TRADE": "#ffc107"}

# League-average baselines the KPI deltas are measured against.
_LEAGUE_AVG_POINTS_FOR = 24
_LEAGUE_AVG_POINTS_AGAINST = 21


def _render_kpis(ctx: AppContext) -> None:
    df = ctx.df
    st.markdown("#### 📊 Franchise Key Performance Indicators")
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    avg_pts_for = df["Points_For"].mean() if "Points_For" in df.columns else 0
    avg_pts_against = (
        df["Points_Against"].mean() if "Points_Against" in df.columns else 0
    )
    win_rate = (
        df["Result"].value_counts(normalize=True).get("WIN", 0) * 100
        if "Result" in df.columns else 0
    )
    pts_for_delta = avg_pts_for - _LEAGUE_AVG_POINTS_FOR
    pts_against_delta = avg_pts_against - _LEAGUE_AVG_POINTS_AGAINST

    with kpi1:
        st.markdown(theme.kpi_card_html(
            "Avg Points Scored", f"{avg_pts_for:.1f}",
            f"{abs(pts_for_delta):.1f} vs League Avg", pts_for_delta >= 0,
        ), unsafe_allow_html=True)
    with kpi2:
        # Lower points allowed is better — a negative delta (allowing fewer
        # than league avg) is the "good" direction here, so it's green.
        st.markdown(theme.kpi_card_html(
            "Avg Points Allowed", f"{avg_pts_against:.1f}",
            f"{abs(pts_against_delta):.1f} vs League Avg", pts_against_delta <= 0,
        ), unsafe_allow_html=True)
    with kpi3:
        st.markdown(theme.kpi_card_html("Win Rate", f"{win_rate:.1f}%"),
                    unsafe_allow_html=True)
    with kpi4:
        st.markdown(theme.kpi_card_html("Games Tracked", str(len(df))),
                    unsafe_allow_html=True)


def _render_franchise_home(ctx: AppContext) -> None:
    st.markdown("#### 🏠 Franchise Home")

    wins, losses = analytics.record_from_log(ctx.df)
    cap = cached_cap_summary(ctx.my_team, ctx.extra_players)
    net_cap = cap["total_savings"] - cap["total_penalty"]
    needs = analytics.top_needs(
        cached_positional_needs(ctx.my_team, ctx.extra_players))
    moves = analytics.actionable_moves(
        cached_roster_verdicts(ctx.my_team, ctx.extra_players))

    col1, col2, col3 = st.columns(3)

    with col1:
        net_color = "#10b981" if net_cap >= 0 else "#ef4444"
        st.markdown(f"""
        <div class="trade-card">
            <div style="color:#94a3b8; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em;">Record &amp; Cap — {ctx.my_team}</div>
            <div style="font-size:1.8rem; font-weight:800; color:#f1f5f9; margin-top:4px;">{wins}-{losses}</div>
            <div style="color:#94a3b8; font-size:0.85rem; margin-top:8px;">
                Net Cap: <span style="color:{net_color}; font-weight:700;">${net_cap:+.1f}M</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        if needs:
            needs_html = "".join(
                f'<div style="display:flex; justify-content:space-between; margin-top:6px;">'
                f'<span style="color:#e2e8f0;">{n["pos"]}</span>'
                f'<span style="color:{n["color"]}; font-weight:700; font-size:0.85rem;">{n["level"]}</span>'
                f'</div>'
                for n in needs
            )
        else:
            needs_html = ('<div style="color:#94a3b8; margin-top:6px;">'
                          'No pressing needs — roster is set everywhere.</div>')
        st.markdown(f"""
        <div class="trade-card">
            <div style="color:#94a3b8; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em;">Top Needs</div>
            {needs_html}
        </div>
        """, unsafe_allow_html=True)

    with col3:
        if moves:
            moves_html = "".join(
                f'<div style="display:flex; justify-content:space-between; margin-top:6px;">'
                f'<span style="color:#e2e8f0;">{v["Name"]} '
                f'<span style="color:#64748b; font-size:0.78rem;">({v["Pos"]})</span></span>'
                f'<span style="color:{_VERDICT_COLORS.get(v["Verdict"], "#94a3b8")}; '
                f'font-weight:700; font-size:0.85rem;">{v["Verdict"]}</span>'
                f'</div>'
                for v in moves
            )
        else:
            moves_html = ('<div style="color:#94a3b8; margin-top:6px;">'
                          'No cut or trade candidates right now.</div>')
        st.markdown(f"""
        <div class="trade-card">
            <div style="color:#94a3b8; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em;">Actionable Roster Moves</div>
            {moves_html}
        </div>
        """, unsafe_allow_html=True)


def render_empty_data_guard(ctx: AppContext) -> None:
    """Import instructions shown when no games have been loaded yet."""
    if not ctx.df.empty:
        return
    st.warning("🚀 **No game data loaded yet!**")
    st.markdown("""
    Get started by importing your franchise data:
    1. **Google Sheet Sync** — Paste a published CSV URL in the sidebar
    2. **Upload CSV/Excel** — Use the sidebar file uploader
    3. **Local CSV** — Place `game_logs.csv` in the `data/` folder

    The Roster Explorer, Season Awards, Coach DNA, and Progression tabs
    will still work using your roster data.
    """)


def render(ctx: AppContext) -> None:
    _render_kpis(ctx)
    theme.divider()
    _render_franchise_home(ctx)
    theme.divider()
