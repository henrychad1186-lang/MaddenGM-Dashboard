"""Coach DNA tab — coaching archetype and play-style radar."""

import plotly.graph_objects as go
import streamlit as st

from views import theme
from views.cache import cached_coach_dna
from views.context import AppContext


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "🎯", "Head Coach DNA Profile",
        "Your coaching identity, computed from your franchise game data")

    dna = cached_coach_dna(ctx.df)
    if dna is None:
        st.warning("Need at least 3 games with Pass/Rush data for Coach DNA analysis.")
        return

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(25,25,55,0.95), rgba(45,45,75,0.8));
        border: 1px solid rgba(99,102,241,0.3); border-radius: 20px;
        padding: 1.5rem; text-align: center; margin-bottom: 1rem;">
        <div style="font-size: 2rem; font-weight: 900; color: #6366f1;">{dna['archetype']}</div>
        <div style="color: #aaa; margin-top: 0.3rem;">
            {dna['win_pct']:.0f}% Win Rate · {dna['avg_pf']:.1f} PPG ·
            {dna['pass_pct']:.0f}/{dna['rush_pct']:.0f} Pass/Rush Split</div>
    </div>
    """, unsafe_allow_html=True)

    categories = list(dna["axes"])
    values = [dna["axes"][c] for c in categories]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor="rgba(99,102,241,0.2)",
        line=dict(color="#6366f1", width=2),
        name="Your DNA",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor="rgba(255,255,255,0.1)"),
            bgcolor="rgba(0,0,0,0)",
        ),
        template="plotly_dark",
        showlegend=False,
        title="Coaching DNA Radar",
        margin=dict(t=60, b=30),
    )
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Pass %", f"{dna['pass_pct']:.0f}%")
    with c2:
        st.metric("Rush %", f"{dna['rush_pct']:.0f}%")
    with c3:
        st.metric("Avg TO/G", f"{dna['avg_to']:.1f}")
    with c4:
        st.metric("Avg Takeaways/G", f"{dna['avg_takeaways']:.1f}")
    with c5:
        st.metric("Avg Sacks/G", f"{dna['avg_sacks']:.1f}")
