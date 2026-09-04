"""Progression tab — OVR snapshots over time and biggest movers."""

import streamlit as st

from src.progression import get_movers, get_progression, snapshot_roster
from views import theme
from views.context import AppContext


def _render_mover(mover: dict, gaining: bool) -> None:
    color = "#00e676" if gaining else "#ff5252"
    tint = "rgba(0,230,118,0.1)" if gaining else "rgba(255,82,82,0.1)"
    delta = f"+{mover['Delta']}" if gaining else str(mover["Delta"])
    st.markdown(f"""
    <div style="background: {tint}; border-left: 3px solid {color};
        border-radius: 8px; padding: 0.5rem 0.8rem; margin-bottom: 0.4rem;">
        <span style="font-weight:700; color:white;">{mover['Name']}</span>
        <span style="color:#aaa;"> {mover['Pos']}</span>
        <span style="float:right; color:{color}; font-weight:800;">{delta} ({mover['Start_OVR']}→{mover['Current_OVR']})</span>
    </div>
    """, unsafe_allow_html=True)


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "📈", "Player Progression Tracker",
        "Snapshot your roster OVRs over time to track development")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        snap_season = st.number_input("Season", min_value=1, max_value=30,
                                      value=1, key="snap_season")
    with c2:
        snap_week = st.number_input("Week", min_value=1, max_value=22,
                                    value=1, key="snap_week")
    with c3:
        if st.button("📸 Save Current OVR Snapshot", type="primary"):
            count = snapshot_roster(ctx.my_team, snap_season, snap_week)
            st.success(f"Saved {count} player OVRs for "
                       f"Season {snap_season}, Week {snap_week}!")

    movers = get_movers(ctx.my_team)
    if movers["gainers"] or movers["losers"]:
        mov1, mov2 = st.columns(2)
        with mov1:
            st.markdown("##### 📈 Biggest Gainers")
            for gainer in movers["gainers"]:
                _render_mover(gainer, gaining=True)
        with mov2:
            st.markdown("##### 📉 Biggest Declines")
            for loser in movers["losers"]:
                _render_mover(loser, gaining=False)
    else:
        st.info("💡 Save at least 2 snapshots at different weeks to see progression "
                "data. Click the button above to save your first snapshot!")

    prog_log = get_progression(ctx.my_team)
    if not prog_log.empty:
        st.markdown("##### 📚 Full Progression Log")
        st.dataframe(prog_log, hide_index=True,
                     use_container_width=True, height=300)
