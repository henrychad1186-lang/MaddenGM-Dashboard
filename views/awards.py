"""Season Awards tab — MVP, DPOY, ROY, Iron Man, Best Contract."""

import streamlit as st

from views import theme
from views.cache import cached_roster, cached_season_awards
from views.context import AppContext


def _render_award(award: dict) -> None:
    title, color, desc = award["title"], award["color"], award["desc"]
    icon, label = title.split(" ", 1)
    player = award["player"]

    if player is None:
        st.markdown(f"""
        <div style="background: rgba(25,25,55,0.5); border: 1px solid #333;
            border-radius: 16px; padding: 1.2rem; text-align: center; color: #666;">
            <div style="font-size: 2.5rem;">{icon}</div>
            <div>{label}</div>
            <div style="font-size: 0.8rem;">No eligible players</div>
        </div>
        """, unsafe_allow_html=True)
        return

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(25,25,55,0.95), rgba(45,45,75,0.8));
        border: 2px solid {color}; border-radius: 16px; padding: 1.2rem;
        text-align: center;">
        <div style="font-size: 2.5rem;">{icon}</div>
        <div style="font-size: 0.9rem; font-weight: 800; color: {color};
            margin: 0.3rem 0;">{label}</div>
        <div style="font-size: 1.1rem; font-weight: 700; color: white;">
            {player['Name']}</div>
        <div style="color: #aaa; font-size: 0.85rem;">
            {player['Pos']} · {int(player['OVR'])} OVR · Age {int(player['Age'])}</div>
        <div style="color: #666; font-size: 0.7rem; margin-top: 0.4rem;">{desc}</div>
    </div>
    """, unsafe_allow_html=True)


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "🏆", "Season Awards",
        "Auto-generated awards based on your current roster data")

    if cached_roster(ctx.my_team, "All", ctx.extra_players).empty:
        st.info("No roster data available for awards.")
        return

    awards = cached_season_awards(ctx.my_team, ctx.extra_players)
    cols = st.columns(len(awards))
    for col, award in zip(cols, awards):
        with col:
            _render_award(award)
