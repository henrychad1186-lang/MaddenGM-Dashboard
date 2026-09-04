"""Scheme Performance tab — strategy map, head-to-head, season momentum."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import analytics
from views import theme
from views.cache import cached_momentum, cached_scheme_stats
from views.context import AppContext


def _render_strategy_map(df: pd.DataFrame) -> None:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("#### TOP vs Score Differential by Scheme")
        if "TOP_Mins" in df.columns and "Score_Diff" in df.columns:
            scatter_df = df.copy()
            if "Points_For" in scatter_df.columns:
                scatter_df["_size"] = pd.to_numeric(
                    scatter_df["Points_For"], errors="coerce"
                ).fillna(1).clip(lower=1)
            fig = px.scatter(
                scatter_df,
                x="TOP_Mins",
                y="Score_Diff",
                color="Playbook" if "Playbook" in scatter_df.columns else None,
                size="_size" if "Points_For" in scatter_df.columns else None,
                hover_data=["Opponent"] if "Opponent" in scatter_df.columns else None,
                template="plotly_dark",
                title="Madden 27 Strategy Map",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Insufficient data for Strategy Map.")
    with col2:
        st.markdown("#### Scheme Efficiency")
        if "Playbook" in df.columns and "Points_For" in df.columns:
            scheme_perf = df.groupby("Playbook")["Points_For"].mean().reset_index()
            st.dataframe(
                scheme_perf.style.format({"Points_For": "{:.1f}"}),
                hide_index=True,
            )
        else:
            st.info("Playbook or Points_For data not found.")


def _render_scheme_card(scheme: str, s: dict) -> None:
    win_color = "#00e676" if s["Win%"] >= 50 else "#ff5252"
    margin_color = "#00e676" if s["Avg Margin"] > 0 else "#ff5252"
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(25,25,55,0.9), rgba(45,45,75,0.7));
        border: 1px solid rgba(99,102,241,0.3); border-radius: 16px; padding: 1.2rem;">
        <div style="font-size:1.2rem; font-weight:800; color:#6366f1; margin-bottom:0.8rem;">
            {scheme}</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem;">
            <div style="color:#aaa;">Record</div>
            <div style="color:{win_color}; font-weight:700;">{s['Record']} ({s['Win%']}%)</div>
            <div style="color:#aaa;">PPG</div>
            <div style="color:white; font-weight:700;">{s['PPG']}</div>
            <div style="color:#aaa;">Opp PPG</div>
            <div style="color:white; font-weight:700;">{s['Opp PPG']}</div>
            <div style="color:#aaa;">Avg Margin</div>
            <div style="color:{margin_color}; font-weight:700;">{s['Avg Margin']:+.1f}</div>
            <div style="color:#aaa;">Pass YPG</div>
            <div style="color:white;">{s['Pass YPG']}</div>
            <div style="color:#aaa;">Rush YPG</div>
            <div style="color:white;">{s['Rush YPG']}</div>
            <div style="color:#aaa;">Total YPG</div>
            <div style="color:white; font-weight:700;">{s['Total YPG']}</div>
            <div style="color:#aaa;">TO/Game</div>
            <div style="color:{'#ff5252' if s['TO/G'] > 1 else '#00e676'};">{s['TO/G']}</div>
            <div style="color:#aaa;">Takeaways/G</div>
            <div style="color:{'#00e676' if s['Takeaways/G'] >= 1.5 else 'white'};">{s['Takeaways/G']}</div>
            <div style="color:#aaa;">Sacks/G</div>
            <div style="color:white;">{s['Sacks/G']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_head_to_head(df: pd.DataFrame) -> None:
    scheme_stats = cached_scheme_stats(df)
    if len(scheme_stats) <= 1:
        return

    st.markdown("---")
    st.markdown("#### 📋 Scheme Head-to-Head Breakdown")

    schemes = list(scheme_stats)
    scheme_cols = st.columns(len(schemes))
    for i, scheme in enumerate(schemes):
        with scheme_cols[i]:
            _render_scheme_card(scheme, scheme_stats[scheme])

    compare_df = analytics.build_scheme_comparison(scheme_stats)
    fig_compare = px.bar(
        compare_df, x="Metric", y="Value", color="Scheme",
        barmode="group", template="plotly_dark",
        title="Scheme Comparison — Key Averages",
        color_discrete_sequence=["#6366f1", "#10b981"],
    )
    fig_compare.update_layout(yaxis_title="Per Game Average", xaxis_title="")
    st.plotly_chart(fig_compare, use_container_width=True)

    st.markdown("#### 🧠 GM Analysis")
    best_scheme = max(scheme_stats, key=lambda s: scheme_stats[s]["Win%"])
    best = scheme_stats[best_scheme]
    other_scheme = [s for s in schemes if s != best_scheme][0]
    other = scheme_stats[other_scheme]
    st.markdown(f"""
    > **{best_scheme}** is your stronger scheme at **{best['Win%']}% win rate**
    > with a **{best['Avg Margin']:+.1f}** avg margin across {best['Games']} games.
    > It averages **{best['PPG']} PPG** on **{best['Total YPG']} total YPG**.
    >
    > **{other_scheme}** runs a **{other['Win%']}% win rate** ({other['Record']})
    > with **{other['Avg Margin']:+.1f}** avg margin.
    > {'⚠️ The turnover rate is higher at ' + str(other['TO/G']) + '/game.' if other['TO/G'] > best['TO/G'] else ''}
    > {'✅ Better ball security at ' + str(other['TO/G']) + ' TO/game.' if other['TO/G'] <= best['TO/G'] else ''}
    """)


def _render_momentum(df: pd.DataFrame) -> None:
    if "Result" not in df.columns or len(df) <= 1:
        return

    st.markdown("---")
    st.markdown("#### 📈 Season Momentum Tracker")
    momentum_df = cached_momentum(df)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=momentum_df["Game_Num"], y=momentum_df["Win_Pct"],
        name="Win %", mode="lines+markers",
        line=dict(color="#6366f1", width=3),
        marker=dict(
            size=10,
            color=["#00e676" if r == "WIN" else "#ff5252"
                   for r in momentum_df["Result"]],
            line=dict(width=1, color="white"),
        ),
        hovertemplate="Game %{x}: %{y:.1f}% win rate<br>vs %{customdata}",
        customdata=momentum_df["Opponent"],
    ))
    if "Rolling_Margin" in momentum_df.columns:
        fig.add_trace(go.Scatter(
            x=momentum_df["Game_Num"],
            y=momentum_df["Rolling_Margin"],
            name="Rolling Avg Margin (3-game)",
            mode="lines",
            line=dict(color="#10b981", width=2, dash="dot"),
            yaxis="y2",
        ))
    fig.update_layout(
        template="plotly_dark",
        title="Win % & Rolling Point Margin Over the Season",
        xaxis_title="Game #",
        yaxis=dict(title="Cumulative Win %", range=[0, 100]),
        yaxis2=dict(title="Avg Margin (3-game)", overlaying="y", side="right"),
        legend=dict(x=0.01, y=0.99),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    ins1, ins2, ins3 = st.columns(3)
    with ins1:
        st.metric("Final Win %", f"{momentum_df['Win_Pct'].iloc[-1]:.1f}%")
    with ins2:
        streak = analytics.longest_win_streak(momentum_df["Win"])
        st.metric("Best Win Streak", f"{streak} games")
    with ins3:
        st.metric("Peak Win %", f"{momentum_df['Win_Pct'].max():.1f}%")


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "📊", "Scheme Performance",
        "Time of possession, score differential, and momentum by scheme")
    _render_strategy_map(ctx.df)
    _render_head_to_head(ctx.df)
    _render_momentum(ctx.df)
