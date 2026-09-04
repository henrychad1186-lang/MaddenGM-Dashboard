"""Dynasty tab — season archive, franchise timeline, career leaderboards."""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.dynasty import archive_season, get_career_leaders, load_history
from views import theme
from views.context import AppContext


def _render_timeline(history: "list[dict]") -> None:
    st.markdown("#### 📅 Franchise Timeline")
    if not history:
        st.info("No dynasty history yet. Archive your first season below!")
        return

    hist_df = pd.DataFrame(history)
    fig = px.scatter(
        hist_df,
        x="season",
        y="wins",
        color="era",
        size="wins",
        hover_data=["record", "playoff_result", "mvp"],
        template="plotly_dark",
        title="Season Performance by Era",
        labels={"season": "Season", "wins": "Wins"},
    )
    fig.update_traces(marker=dict(line=dict(width=2, color="white")))
    fig.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 📜 The Chronicles")
    for season in reversed(history):
        era_label = season.get("era", "Unknown Era")
        trophy = " 🏆" if "Champion" in season.get("playoff_result", "") else ""
        with st.expander(f"Season {season['season']} — {era_label}{trophy}"):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Record", season.get("record", "N/A"))
                st.metric("Playoff Result", season.get("playoff_result", "N/A"))
            with c2:
                st.metric("MVP", season.get("mvp", "N/A"))
                st.caption(season.get("mvp_stats", ""))
            with c3:
                st.metric("Top Rusher",
                          f"{season.get('top_rusher', 'N/A')} "
                          f"({season.get('rush_yards', 0)} yds)")
                st.metric("Top Receiver",
                          f"{season.get('top_receiver', 'N/A')} "
                          f"({season.get('rec_yards', 0)} yds)")
            if season.get("notes"):
                st.caption(f"📝 {season['notes']}")


def _render_career_leaders(history: "list[dict]") -> None:
    st.markdown("---")
    st.markdown("#### 📊 Career Leaderboard")
    leaders_df = get_career_leaders(history)
    if leaders_df.empty:
        st.info("No career leaders data available yet.")
        return
    st.dataframe(
        leaders_df.style.format({
            "Rush Yds": "{:,.0f}",
            "Rec Yds": "{:,.0f}",
            "Total Yds": "{:,.0f}",
        }),
        hide_index=True,
        use_container_width=True,
    )


def _render_archive_form(history: "list[dict]") -> None:
    st.markdown("---")
    st.markdown("#### 📝 Archive a Season")
    with st.form("archive_season_form", clear_on_submit=True):
        acol1, acol2 = st.columns(2)
        with acol1:
            new_season = st.number_input(
                "Season Year", min_value=2020, max_value=2040, value=2027)
            new_era = st.text_input("Era Name", placeholder="e.g. The Rebuild")
            new_record = st.text_input("Record (W-L)", placeholder="e.g. 11-6")
        with acol2:
            new_playoff = st.text_input(
                "Playoff Result", placeholder="e.g. Divisional Round")
            new_mvp = st.text_input("MVP Player", placeholder="e.g. Jordan Love")
            new_mvp_stats = st.text_input(
                "MVP Stats", placeholder="e.g. 4,200 Yds / 30 TD")
        new_notes = st.text_area(
            "Season Notes", placeholder="Brief summary of the season...")

        submitted = st.form_submit_button("💾 Archive Season")

    if submitted and new_record:
        try:
            wins = int(new_record.split("-")[0])
            losses = int(new_record.split("-")[1])
        except Exception:
            wins, losses = 0, 0

        archive_season({
            "season": int(new_season),
            "era": new_era or "Unknown Era",
            "record": new_record,
            "wins": wins,
            "losses": losses,
            "playoff_result": new_playoff or "N/A",
            "mvp": new_mvp or "N/A",
            "mvp_stats": new_mvp_stats or "",
            "top_rusher": "N/A",
            "rush_yards": 0,
            "top_receiver": "N/A",
            "rec_yards": 0,
            "notes": new_notes,
        }, history)
        st.success(f"✅ Season {new_season} archived under \"{new_era}\"!")
        st.rerun()


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "🏛️", "Dynasty — Franchise Legacy",
        "Season archives, era tracking, and career leaderboards")

    history = load_history()
    _render_timeline(history)
    _render_career_leaders(history)
    _render_archive_form(history)
