"""
Roster Explorer tab — the deepest view of a single team.

Position grades, trade-value leaderboard, cap overview, cut/keep verdicts
and the depth chart all read the same roster, so every section here goes
through `views.cache` rather than recomputing it per section.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.roster import POSITION_GROUPS, ROSTER_WARNINGS, ovr_color, ovr_label
from views import theme
from views.cache import (
    cached_cap_summary,
    cached_position_grades,
    cached_roster,
    cached_roster_verdicts,
    cached_team_summary,
    cached_trade_value_table,
)
from views.context import AppContext

_OFF_POSITIONS = ["QB", "HB", "WR", "TE", "LT", "LG", "C", "RG", "RT"]
_DEF_POSITIONS = ["EDGE", "DT", "MLB", "OLB", "CB", "SS", "FS"]

_TIER_COLORS = {
    "Elite": "#00e676",
    "Great": "#2196f3",
    "Average": "#ffc107",
    "Developing": "#ff5252",
}

_VERDICT_COLORS = {"KEEP": "#00e676", "TRADE": "#ffc107", "CUT": "#ff5252"}
_VERDICT_ICONS = {"KEEP": "✅", "TRADE": "📦", "CUT": "✂️"}

_DEV_ICONS = {"Superstar X": "⭐", "Superstar": "🌟", "Star": "✨", "Normal": ""}


def _style_ovr(val) -> str:
    return f"color: {ovr_color(val)}; font-weight: bold"


def _style_tier(val) -> str:
    return f"color: {_TIER_COLORS.get(val, 'white')}; font-weight: bold"


def _style_trade_value(val) -> str:
    if val >= 700:
        color = "#00e676"
    elif val >= 500:
        color = "#2196f3"
    elif val >= 350:
        color = "#ffc107"
    else:
        color = "#ff5252"
    return f"color: {color}; font-weight: bold"


def _render_data_warnings() -> None:
    if not ROSTER_WARNINGS:
        return
    with st.expander(
        f"⚠️ {len(ROSTER_WARNINGS)} data quality issue(s) found in the roster CSV",
        expanded=False,
    ):
        st.caption(
            "Found automatically when the roster loaded — fix these directly "
            "in `data/packers_roster.csv`. They don't block the app, but "
            "anything flagged here (a garbled name, an out-of-range stat) "
            "will show up as-is everywhere, including AI GM answers.")
        for warning in ROSTER_WARNINGS:
            st.markdown(f"- {warning}")


def _render_roster_table(ctx: AppContext, group: str) -> None:
    roster_df = cached_roster(ctx.my_team, group, ctx.extra_players)
    if roster_df.empty:
        st.info(f"No players found for {ctx.my_team} — {group}")
        return

    display = roster_df[["Name", "Pos", "OVR", "Age", "Dev"]].copy()
    display["Tier"] = display["OVR"].apply(ovr_label)
    display = display.sort_values("OVR", ascending=False).reset_index(drop=True)

    styled = display.style.map(_style_ovr, subset=["OVR"]).map(
        _style_tier, subset=["Tier"])
    st.dataframe(styled, hide_index=True, use_container_width=True, height=500)

    st.markdown("#### Position Breakdown")
    pos_counts = roster_df["Pos"].value_counts().reset_index()
    pos_counts.columns = ["Position", "Count"]
    fig = px.bar(
        pos_counts, x="Position", y="Count",
        template="plotly_dark", color="Count",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _render_trade_value_leaderboard(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 💎 Trade Value Leaderboard")
    st.caption("Players ranked by trade value — factors in OVR, age, position, "
               "dev trait, contract, and athleticism.")

    table = cached_trade_value_table(ctx.my_team, ctx.extra_players)
    if table.empty:
        return
    styled = (
        table.style
        .map(_style_trade_value, subset=["Trade Value"])
        .map(_style_ovr, subset=["OVR"])
        .format({"Trade Value": "{:.1f}"})
    )
    st.dataframe(styled, use_container_width=True, height=450)


def _render_position_grades(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 📊 Position Group Grades")
    grades = cached_position_grades(ctx.my_team, ctx.extra_players)
    if not grades:
        st.info("No position data available.")
        return

    cols = st.columns(4)
    for i, g in enumerate(grades):
        with cols[i % 4]:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(30,30,60,0.9), rgba(50,50,80,0.7));
                border: 1px solid {g['color']}40; border-radius: 14px; padding: 1rem;
                text-align: center; margin-bottom: 0.8rem;">
                <div style="font-size: 2rem; font-weight: 900; color: {g['color']};">{g['grade']}</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: white;">{g['pos']}</div>
                <div style="font-size: 0.8rem; color: #aaa;">{g['count']} players · {g['avg_ovr']} avg</div>
            </div>
            """, unsafe_allow_html=True)


def _render_cap_overview(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 💰 Cap Overview")
    cap = cached_cap_summary(ctx.my_team, ctx.extra_players)
    if not cap["players"]:
        st.info("No contract data available.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Cap Savings", f"${cap['total_savings']:.1f}M")
    with c2:
        st.metric("Total Dead Cap", f"${cap['total_penalty']:.1f}M",
                  delta=f"-${cap['total_penalty']:.1f}M", delta_color="inverse")
    with c3:
        net = cap["total_savings"] - cap["total_penalty"]
        st.metric("Net Cap Position", f"${net:+.1f}M",
                  delta="Healthy" if net > 0 else "Tight",
                  delta_color="normal" if net > 0 else "inverse")

    st.markdown("##### 🔴 Top 5 Dead Cap Hits")
    top_dead = [p for p in cap["players"] if p["Penalty"] > 0][:5]
    if not top_dead:
        st.info("No dead cap obligations found.")
        return
    dead_df = pd.DataFrame(top_dead)
    dead_df["Penalty"] = dead_df["Penalty"].apply(lambda x: f"${x:.2f}M")
    dead_df["Savings"] = dead_df["Savings"].apply(lambda x: f"${x:.2f}M")
    st.dataframe(dead_df, hide_index=True, use_container_width=True)


def _render_cut_or_keep(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### ✂️ Cut or Keep Analyzer")
    verdicts = cached_roster_verdicts(ctx.my_team, ctx.extra_players)
    if not verdicts:
        st.info("No roster data for analysis.")
        return

    counts = {v: 0 for v in _VERDICT_COLORS}
    for v in verdicts:
        counts[v["Verdict"]] = counts.get(v["Verdict"], 0) + 1

    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        st.metric("✅ Keep", counts["KEEP"])
    with ck2:
        st.metric("🟡 Trade Candidates", counts["TRADE"])
    with ck3:
        st.metric("🔴 Cut Candidates", counts["CUT"])

    cols = st.columns(3)
    for i, v in enumerate(verdicts):
        with cols[i % 3]:
            vc = _VERDICT_COLORS[v["Verdict"]]
            vi = _VERDICT_ICONS[v["Verdict"]]
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(25,25,55,0.9), rgba(45,45,75,0.7));
                border: 1px solid {vc}40; border-left: 4px solid {vc};
                border-radius: 12px; padding: 0.8rem; margin-bottom: 0.6rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:800; color:white;">{v['Name']}</span>
                        <span style="color:#aaa; font-size:0.85rem;"> {v['Pos']} · {v['Age']}yo · {v['OVR']} OVR</span>
                    </div>
                    <div style="background:{vc}; color:#000; font-weight:800; padding:2px 10px;
                        border-radius:8px; font-size:0.8rem;">{vi} {v['Verdict']}</div>
                </div>
                <div style="color:#bbb; font-size:0.78rem; margin-top:4px;">{v['Reason']}</div>
                <div style="color:#888; font-size:0.72rem; margin-top:2px;">TV: {v['Trade_Value']:.0f} · Sav: ${v['Savings']:.1f}M · Dead: ${v['Penalty']:.1f}M · Depth: {v['Depth']}</div>
            </div>
            """, unsafe_allow_html=True)


def _render_depth_chart(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 📋 Depth Chart")
    side = st.radio("Unit", ["Offense", "Defense"], horizontal=True, key="dc_unit")
    positions = _OFF_POSITIONS if side == "Offense" else _DEF_POSITIONS

    full_roster = cached_roster(ctx.my_team, "All", ctx.extra_players)
    cols = st.columns(len(positions))
    for i, pos in enumerate(positions):
        with cols[i]:
            pos_players = full_roster[full_roster["Pos"] == pos].sort_values(
                "OVR", ascending=False)
            st.markdown(f"<div style='text-align:center; font-weight:800; "
                        f"color: #6366f1; margin-bottom:4px;'>{pos}</div>",
                        unsafe_allow_html=True)
            for depth, (_, p) in enumerate(pos_players.iterrows()):
                ovr = int(p["OVR"])
                cls = "dc-starter" if depth == 0 else "dc-backup"
                dev_icon = _DEV_ICONS.get(str(p.get("Dev", "Normal")), "")
                # Surnames only — nine columns of full names don't fit.
                name = str(p["Name"])
                short_name = name.split(".")[-1].strip() if "." in name else name
                st.markdown(f"""
                <div class="dc-card {cls}">
                    <div style="font-weight:700; color:white; font-size:0.85rem;">
                        {short_name}
                    </div>
                    <div style="font-size:1.4rem; font-weight:900; color:{ovr_color(ovr)};">
                        {ovr} {dev_icon}
                    </div>
                    <div style="font-size:0.7rem; color:#aaa;">Age {int(p['Age'])}</div>
                </div>
                """, unsafe_allow_html=True)
            if pos_players.empty:
                st.markdown("<div class='dc-card' style='color:#666;'>Empty</div>",
                            unsafe_allow_html=True)


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "📋", "Roster Explorer",
        "Position grades, depth chart, cap overview, and cut-or-keep analysis")

    _render_data_warnings()

    col_filters, col_table = st.columns([1, 3])
    with col_filters:
        st.info(f"Showing: **{ctx.my_team}**")
        group = st.selectbox("Position Group:", POSITION_GROUPS,
                             key="roster_group_select")

        summary = cached_team_summary(ctx.my_team, ctx.extra_players)
        st.markdown("---")
        st.metric("Players", summary["count"])
        st.metric("Avg OVR", summary["avg_ovr"])
        st.metric("Avg Age", summary["avg_age"])
        st.markdown(f"⭐ **Best Player:** {summary.get('best_player', 'N/A')} "
                    f"({summary.get('best_ovr', 'N/A')} OVR)")

    with col_table:
        _render_roster_table(ctx, group)

    _render_trade_value_leaderboard(ctx)
    _render_position_grades(ctx)
    _render_cap_overview(ctx)
    _render_cut_or_keep(ctx)
    _render_depth_chart(ctx)
