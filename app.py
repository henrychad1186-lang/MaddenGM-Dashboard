import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Import new feature modules
from src.trade_engine import (
    DEMO_ROSTERS as TRADE_ROSTERS,
    get_trade_value,
    find_trade_partners,
    evaluate_trade,
)
from src.dynasty import load_history, archive_season, get_career_leaders
from src.roster_analyzer import analyze_roster
from src import ai_gm
from src import ai_client
from src.progression import snapshot_roster, get_progression, get_movers
from src.roster import (
    get_roster,
    get_team_summary,
    ovr_color,
    ovr_label,
    get_position_grades,
    get_cap_summary,
    TEAMS,
    POSITION_GROUPS,
)

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Madden 26 GM War Room",
    layout="wide",
    page_icon="🏈",
)

# ── CUSTOM CSS — Premium Dark Theme ──
st.markdown("""
<style>
/* ── Trade Tab Background & Global ── */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(160deg, #0a0e17 0%, #111827 50%, #0f172a 100%);
}

/* ── Glassmorphism Cards ── */
.trade-card {
    background: rgba(30, 41, 59, 0.65);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.trade-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(99, 102, 241, 0.2);
}

/* ── Player Spotlight Card ── */
.player-spotlight {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(16, 185, 129, 0.10));
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99, 102, 241, 0.35);
    border-radius: 20px;
    padding: 1.8rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.player-spotlight::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%);
    animation: pulse-glow 4s ease-in-out infinite;
}
@keyframes pulse-glow {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.05); }
}

/* ── Interest Bar ── */
.interest-bar {
    background: rgba(30, 41, 59, 0.5);
    border-radius: 8px;
    overflow: hidden;
    height: 10px;
    margin: 4px 0 8px 0;
}
.interest-fill {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #6366f1, #10b981);
    transition: width 0.6s ease;
}

/* ── Trade Verdict Badges ── */
.verdict-accept {
    background: linear-gradient(135deg, #065f46, #10b981);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}
.verdict-lean {
    background: linear-gradient(135deg, #92400e, #f59e0b);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}
.verdict-decline {
    background: linear-gradient(135deg, #991b1b, #ef4444);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}

/* ── Section Dividers ── */
.section-glow {
    height: 2px;
    background: linear-gradient(90deg, transparent, #6366f1, #10b981, transparent);
    margin: 1.2rem 0;
    border: none;
}

/* ── Stat Pill ── */
.stat-pill {
    display: inline-block;
    background: rgba(99, 102, 241, 0.2);
    border: 1px solid rgba(99, 102, 241, 0.4);
    border-radius: 20px;
    padding: 4px 14px;
    margin: 3px;
    font-size: 0.85rem;
    color: #c7d2fe;
}

/* ── Global Premium Enhancements ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d0d22 0%, #1a1a3e 100%);
    border-right: 1px solid rgba(99, 102, 241, 0.2);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 8px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background: rgba(20, 20, 50, 0.6);
    border-radius: 10px 10px 0 0;
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-bottom: none;
    padding: 0.6rem 1.2rem;
    transition: background 0.2s;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: rgba(99, 102, 241, 0.2) !important;
    border-color: rgba(99, 102, 241, 0.4) !important;
}
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(20,20,50,0.8), rgba(40,40,70,0.6));
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-radius: 12px;
    padding: 1rem;
}
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

/* ── Depth Chart Cards ── */
.dc-card {
    background: linear-gradient(135deg, rgba(25,25,55,0.9), rgba(45,45,75,0.7));
    border-radius: 12px;
    padding: 0.7rem;
    text-align: center;
    border: 1px solid rgba(99,102,241,0.2);
    margin-bottom: 0.5rem;
    transition: transform 0.2s, box-shadow 0.2s;
}
.dc-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(99,102,241,0.15);
}
.dc-starter { border-left: 3px solid #00e676; }
.dc-backup  { border-left: 3px solid #ffc107; opacity: 0.85; }
</style>
""", unsafe_allow_html=True)

st.title("Madden NFL 26: Franchise Strategy Audit")
st.markdown(
    "Analysis updated for the **2028 Season**. "
    "Utilizing new **Coach DNA** and **Wear & Tear** metrics."
)

# --- 1. DATA ENGINE ---
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_GAME_LOGS_CSV = os.path.join(_DATA_DIR, "game_logs.csv")


@st.cache_data(ttl=120, show_spinner=False)
def _read_csv_cached(path_or_url: str) -> pd.DataFrame:
    """Cache game log CSV reads to avoid repeated disk/network fetches on rerun."""
    return pd.read_csv(path_or_url)


st.sidebar.header("Data Import")

# ── Live Google Sheet Sync ──
sheet_url = st.sidebar.text_input(
    "📡 Google Sheet CSV URL",
    value="",
    placeholder="Paste your published CSV link",
    help="Publish your Google Sheet (File → Share → Publish to web → CSV) and paste the URL here.",
)

uploaded_file = st.sidebar.file_uploader(
    "Or upload CSV/Excel", type=["csv", "xlsx"]
)

df = None  # will be set by one of the branches

if sheet_url and sheet_url.strip():
    try:
        df = _read_csv_cached(sheet_url.strip())
        # Cache locally so it works offline next time
        try:
            df.to_csv(_GAME_LOGS_CSV, index=False)
        except OSError:
            pass  # read-only filesystem (e.g. Streamlit Cloud)
        st.sidebar.success(f"📡 Live Sheet Synced — {len(df)} games!")
    except Exception as e:
        st.sidebar.warning(f"Sheet sync failed: {e}")
        st.sidebar.info("Falling back to local data.")

if df is None and uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.sidebar.success("Custom Data Loaded!")
    except Exception as e:
        st.error(f"Error loading file: {e}")
        st.stop()

if df is None and os.path.exists(_GAME_LOGS_CSV):
    df = _read_csv_cached(_GAME_LOGS_CSV)
    st.sidebar.success("📊 Local Franchise Data Loaded!")

if df is None:
    # Fallback demo data
    data = [
        {"Game_ID": "G1", "Team": "DEMO", "Opponent": "JAX",
         "Score_Final": "34-10", "TOP": "27:45", "Playbook": "WestCoast", "Fatigue": 12},
    ]
    df = pd.DataFrame(data)
    st.sidebar.info("Using Demo Data")

# --- DATA PRE-PROCESSING ---
# Handle Score_Final format (old) or direct Points_For/Points_Against (new)
if "Score_Final" in df.columns:
    try:
        df[["Points_For", "Points_Against"]] = (
            df["Score_Final"].str.split("-", expand=True).astype(int)
        )
        df["Score_Diff"] = df["Points_For"] - df["Points_Against"]
        df["Result"] = df["Score_Diff"].apply(
            lambda x: "WIN" if x > 0 else "LOSS"
        )
    except Exception:
        st.warning("Could not parse Score_Final. Ensure format is '35-10'.")
elif "Points_For" in df.columns and "Points_Against" in df.columns:
    df["Points_For"] = pd.to_numeric(df["Points_For"], errors="coerce")
    df["Points_Against"] = pd.to_numeric(df["Points_Against"], errors="coerce")
    df["Score_Diff"] = df["Points_For"] - df["Points_Against"]
    # Normalize Result: W → WIN, L → LOSS
    if "Result" in df.columns:
        df["Result"] = df["Result"].map(
            {"W": "WIN", "L": "LOSS", "WIN": "WIN", "LOSS": "LOSS"}
        ).fillna("LOSS")
    else:
        df["Result"] = df["Score_Diff"].apply(
            lambda x: "WIN" if x > 0 else "LOSS"
        )

if "TOP" in df.columns:
    def parse_top(x):
        if isinstance(x, str) and ":" in x:
            parts = x.split(":")
            try:
                return int(parts[0]) + int(parts[1]) / 60
            except ValueError:
                return None
        return x
    try:
        df["TOP_Mins"] = df["TOP"].apply(parse_top)
    except Exception:
        pass

# --- GLOBAL TEAM SELECTOR ---
st.sidebar.header("My Team")
MY_TEAM = st.sidebar.selectbox(
    "Select Your Franchise Team", TEAMS, index=TEAMS.index("GB") if "GB" in TEAMS else 0,
    key="global_team_select",
)

# --- AI GM ASSISTANT — SESSION-SCOPED ROSTER ADDITIONS ---
# Players added via the AI GM Assistant tab live only in this browser
# session's state, never in the shared roster/trade_engine module globals,
# so one visitor's additions never leak into another visitor's view.
if "ai_gm_players" not in st.session_state:
    st.session_state.ai_gm_players = []
AI_GM_EXTRA = st.session_state.ai_gm_players

if AI_GM_EXTRA:
    # Keep _id (unlike the roster/cap paths, which never expose it to the
    # UI) — the Trade Machine selects players by Name, and _id is the only
    # thing that could disambiguate same-named players there later. It's
    # an inert extra column for get_trade_value() and the CPU-side rows.
    _ai_gm_trade_df = pd.DataFrame(AI_GM_EXTRA)
    EFFECTIVE_TRADE_ROSTERS = pd.concat(
        [TRADE_ROSTERS, _ai_gm_trade_df], ignore_index=True)
else:
    EFFECTIVE_TRADE_ROSTERS = TRADE_ROSTERS

# --- 2. WIN PROBABILITY PREDICTOR ---
st.sidebar.header("Coach DNA: Live Predictor")
st.sidebar.info("Uses Madden 26 Real-Time Coaching AI logic.")
user_top = st.sidebar.slider(
    "Current Time of Possession (Mins)", 0, 45, 20
)
user_fatigue = st.sidebar.slider(
    "Team Wear & Tear (%)", 0, 100, 15
)

win_prob = 1 / (1 + np.exp(-(0.1 * user_top - 0.05 * user_fatigue)))
st.sidebar.metric(
    "Projected Win Probability", f"{win_prob * 100:.1f}%"
)
st.sidebar.progress(float(win_prob))

# --- EMPTY DATA GUARD ---
if df.empty or len(df) == 0:
    st.warning("🚀 **No game data loaded yet!**")
    st.markdown("""
    Get started by importing your franchise data:
    1. **Google Sheet Sync** — Paste a published CSV URL in the sidebar
    2. **Upload CSV/Excel** — Use the sidebar file uploader
    3. **Local CSV** — Place `game_logs.csv` in the `data/` folder

    The Roster Explorer, Season Awards, Coach DNA, and Progression tabs
    will still work using your roster data.
    """)

# --- 3. DASHBOARD VISUALS ---
st.markdown("### Franchise Key Performance Indicators (KPIs)")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

avg_pts_for = df["Points_For"].mean() if "Points_For" in df.columns else 0
avg_pts_against = (
    df["Points_Against"].mean() if "Points_Against" in df.columns else 0
)
win_rate = (
    df["Result"].value_counts(normalize=True).get("WIN", 0) * 100
    if "Result" in df.columns
    else 0
)

with kpi1:
    st.metric(
        "Avg Points Scored",
        f"{avg_pts_for:.1f}",
        delta=f"{avg_pts_for - 24:.1f} vs League Avg",
    )
with kpi2:
    st.metric(
        "Avg Points Allowed",
        f"{avg_pts_against:.1f}",
        delta=f"{avg_pts_against - 21:.1f} vs League Avg",
        delta_color="inverse",
    )
with kpi3:
    st.metric("Win Rate", f"{win_rate:.1f}%")
with kpi4:
    st.metric("Games Tracked", len(df))

st.divider()

# ──────────────────────────────────────────────────────
# TABS — Original + New Features
# ──────────────────────────────────────────────────────
tabs = st.tabs([
    "📊 Scheme Performance",
    "💪 Wear & Tear",
    "🏈 Trade Machine",
    "🏛️ Dynasty",
    "📋 Roster Explorer",
    "🏆 Season Awards",
    "🎯 Coach DNA",
    "📈 Progression",
    "🗂️ Raw Data",
    "🤖 AI GM Assistant",
])

# ── TAB 1: Scheme Performance ──
with tabs[0]:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("TOP vs Score Differential by Scheme")
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
                hover_data=[
                    "Opponent"] if "Opponent" in scatter_df.columns else None,
                template="plotly_dark",
                title="Madden 26 Strategy Map",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Insufficient data for Strategy Map.")
    with col2:
        st.subheader("Scheme Efficiency")
        if "Playbook" in df.columns and "Points_For" in df.columns:
            scheme_perf = (
                df.groupby("Playbook")["Points_For"]
                .mean()
                .reset_index()
            )
            st.dataframe(
                scheme_perf.style.format({"Points_For": "{:.1f}"}),
                hide_index=True,
            )
        else:
            st.info("Playbook or Points_For data not found.")

    # ── Scheme Head-to-Head Breakdown ──
    if "Playbook" in df.columns and len(df["Playbook"].dropna().unique()) > 1:
        st.markdown("---")
        st.subheader("📋 Scheme Head-to-Head Breakdown")

        schemes = df["Playbook"].dropna().unique().tolist()
        scheme_stats = {}
        for scheme in schemes:
            s_df = df[df["Playbook"] == scheme]
            wins = (s_df["Result"] == "WIN").sum(
            ) if "Result" in s_df.columns else 0
            losses = len(s_df) - wins
            scheme_stats[scheme] = {
                "Games": len(s_df),
                "Record": f"{wins}-{losses}",
                "Win%": round(wins / max(len(s_df), 1) * 100, 1),
                "PPG": round(s_df["Points_For"].mean(), 1) if "Points_For" in s_df.columns else 0,
                "Opp PPG": round(s_df["Points_Against"].mean(), 1) if "Points_Against" in s_df.columns else 0,
                "Pass YPG": round(s_df["Pass_Yards"].mean(), 1) if "Pass_Yards" in s_df.columns else 0,
                "Rush YPG": round(s_df["Rush_Yards"].mean(), 1) if "Rush_Yards" in s_df.columns else 0,
                "Total YPG": round(s_df["Total_Yards"].mean(), 1) if "Total_Yards" in s_df.columns else 0,
                "TO/G": round(s_df["Turnovers"].mean(), 2) if "Turnovers" in s_df.columns else 0,
                "Takeaways/G": round(s_df["Takeaways"].mean(), 2) if "Takeaways" in s_df.columns else 0,
                "Sacks/G": round(s_df["Sacks_For"].mean(), 1) if "Sacks_For" in s_df.columns else 0,
                "Avg Margin": round(s_df["Score_Diff"].mean(), 1) if "Score_Diff" in s_df.columns else 0,
            }

        # Side-by-side scheme cards
        scheme_cols = st.columns(len(schemes))
        for i, scheme in enumerate(schemes):
            s = scheme_stats[scheme]
            win_color = "#00e676" if s["Win%"] >= 50 else "#ff5252"
            margin_color = "#00e676" if s["Avg Margin"] > 0 else "#ff5252"
            with scheme_cols[i]:
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

        # Grouped bar chart comparison
        compare_metrics = ["PPG", "Opp PPG",
                           "Pass YPG", "Rush YPG", "Total YPG"]
        compare_rows = []
        for scheme in schemes:
            for metric in compare_metrics:
                compare_rows.append({
                    "Scheme": scheme, "Metric": metric,
                    "Value": scheme_stats[scheme][metric],
                })
        compare_df = pd.DataFrame(compare_rows)
        fig_compare = px.bar(
            compare_df, x="Metric", y="Value", color="Scheme",
            barmode="group", template="plotly_dark",
            title="Scheme Comparison — Key Averages",
            color_discrete_sequence=["#6366f1", "#10b981"],
        )
        fig_compare.update_layout(yaxis_title="Per Game Average",
                                  xaxis_title="")
        st.plotly_chart(fig_compare, use_container_width=True)

        # GM Text Analysis
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

    # ── Win Probability / Momentum Curve ──
    if "Result" in df.columns and len(df) > 1:
        st.markdown("---")
        st.subheader("📈 Season Momentum Tracker")
        momentum_df = df.copy()
        momentum_df = momentum_df.reset_index(drop=True)
        momentum_df["Game_Num"] = range(1, len(momentum_df) + 1)
        momentum_df["Win"] = (momentum_df["Result"] == "WIN").astype(int)
        momentum_df["Cum_Wins"] = momentum_df["Win"].cumsum()
        momentum_df["Win_Pct"] = (
            momentum_df["Cum_Wins"] / momentum_df["Game_Num"] * 100
        ).round(1)
        if "Score_Diff" in momentum_df.columns:
            momentum_df["Rolling_Margin"] = (
                momentum_df["Score_Diff"].rolling(
                    3, min_periods=1).mean().round(1)
            )

        fig_momentum = go.Figure()
        # Win % line
        fig_momentum.add_trace(go.Scatter(
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
        # Rolling margin line (secondary y-axis)
        if "Rolling_Margin" in momentum_df.columns:
            fig_momentum.add_trace(go.Scatter(
                x=momentum_df["Game_Num"],
                y=momentum_df["Rolling_Margin"],
                name="Rolling Avg Margin (3-game)",
                mode="lines",
                line=dict(color="#10b981", width=2, dash="dot"),
                yaxis="y2",
            ))
        fig_momentum.update_layout(
            template="plotly_dark",
            title="Win % & Rolling Point Margin Over the Season",
            xaxis_title="Game #",
            yaxis=dict(title="Cumulative Win %", range=[0, 100]),
            yaxis2=dict(title="Avg Margin (3-game)", overlaying="y",
                        side="right"),
            legend=dict(x=0.01, y=0.99),
            hovermode="x unified",
        )
        st.plotly_chart(fig_momentum, use_container_width=True)

        # Quick insights
        best_streak = 0
        curr_streak = 0
        for w in momentum_df["Win"]:
            curr_streak = curr_streak + 1 if w else 0
            best_streak = max(best_streak, curr_streak)
        final_pct = momentum_df["Win_Pct"].iloc[-1]
        ins1, ins2, ins3 = st.columns(3)
        with ins1:
            st.metric("Final Win %", f"{final_pct:.1f}%")
        with ins2:
            st.metric("Best Win Streak", f"{best_streak} games")
        with ins3:
            peak = momentum_df["Win_Pct"].max()
            st.metric("Peak Win %", f"{peak:.1f}%")

# ── TAB 2: Wear & Tear Impact ──
with tabs[1]:
    st.subheader("The 'Wear & Tear' Cost")
    st.write(
        "How turnovers, defensive breakdowns, and fatigue impact your franchise."
    )

    if "Fatigue" in df.columns and "Points_For" in df.columns:
        fig_fatigue = px.bar(
            df.sort_values("Fatigue"),
            x="Fatigue",
            y="Points_For",
            color="Result" if "Result" in df.columns else None,
            title="Fatigue Level vs Offensive Production",
            template="plotly_dark",
        )
        st.plotly_chart(fig_fatigue, use_container_width=True)

    # Turnovers impact
    if "Turnovers" in df.columns and "Points_For" in df.columns:
        wt1, wt2 = st.columns(2)
        with wt1:
            fig_to = px.scatter(
                df, x="Turnovers", y="Points_For",
                color="Result" if "Result" in df.columns else None,
                color_discrete_map={"WIN": "#00e676", "LOSS": "#ff5252"},
                size="Total_Yards" if "Total_Yards" in df.columns else None,
                hover_data=["Opponent"],
                title="Turnovers vs Points Scored",
                template="plotly_dark",
            )
            st.plotly_chart(fig_to, use_container_width=True)
        with wt2:
            if "Total_Yards_Allowed" in df.columns and "Takeaways" in df.columns:
                fig_def = px.scatter(
                    df, x="Total_Yards_Allowed", y="Takeaways",
                    color="Result" if "Result" in df.columns else None,
                    color_discrete_map={"WIN": "#00e676", "LOSS": "#ff5252"},
                    hover_data=["Opponent"],
                    title="Yards Allowed vs Takeaways",
                    template="plotly_dark",
                )
                st.plotly_chart(fig_def, use_container_width=True)

    # Rush vs Pass balance
    if "Pass_Yards" in df.columns and "Rush_Yards" in df.columns:
        balance_df = df[["Opponent", "Pass_Yards",
                         "Rush_Yards", "Result"]].dropna()
        fig_bal = px.bar(
            balance_df, x="Opponent", y=["Pass_Yards", "Rush_Yards"],
            color_discrete_map={
                "Pass_Yards": "#6366f1", "Rush_Yards": "#10b981"},
            title="Pass vs Rush Yardage by Game",
            template="plotly_dark", barmode="stack",
        )
        fig_bal.update_layout(legend_title="Yard Type",
                              yaxis_title="Yards",
                              xaxis_title="Opponent")
        st.plotly_chart(fig_bal, use_container_width=True)

# ── TAB 3: Trade Machine ──
with tabs[2]:
    # Section header with gradient divider
    st.markdown('<div style="text-align:center;"><h2 style="'
                'background: linear-gradient(90deg, #6366f1, #10b981);'
                '-webkit-background-clip: text; -webkit-text-fill-color: transparent;'
                'font-size: 2rem; margin-bottom: 0;">'
                '🏈 War Room 2.0</h2>'
                '<p style="color:#94a3b8; font-size:0.95rem;">'
                'Find trade partners · Evaluate deals · AI counter-offers</p></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-glow"></div>', unsafe_allow_html=True)

    tmcol1, tmcol2 = st.columns([1, 1], gap="large")

    # ── LEFT COLUMN — Player Scout & Partner Finder ──
    with tmcol1:
        st.markdown("#### 🔍 Player Scout")
        user_roster = EFFECTIVE_TRADE_ROSTERS[EFFECTIVE_TRADE_ROSTERS["Team"] == MY_TEAM].copy()
        player_names = user_roster["Name"].tolist()
        selected_player_name = st.selectbox(
            "Select a player to shop:", player_names, key="trade_player_select"
        )

        selected_row = user_roster[user_roster["Name"]
                                   == selected_player_name].iloc[0]
        selected_player = selected_row.to_dict()
        player_value = get_trade_value(selected_player)

        # ── Player Spotlight Card ──
        dev_colors = {"Superstar X": "#f59e0b", "Superstar": "#a78bfa",
                      "Star": "#60a5fa", "Normal": "#94a3b8"}
        dev_c = dev_colors.get(
            str(selected_player.get('Dev', 'Normal')), '#94a3b8')
        ovr_val = int(selected_player.get('OVR', 70))
        ovr_c = "#00e676" if ovr_val >= 90 else "#2196f3" if ovr_val >= 80 else "#ffc107" if ovr_val >= 70 else "#ff5252"

        # Stat pills for available physical attributes
        pills_html = ""
        for attr_key, attr_label in [("SPD", "SPD"), ("ACC", "ACC"), ("AGI", "AGI"),
                                     ("STR", "STR"), ("AWR", "AWR"), ("COD", "COD")]:
            val = selected_player.get(attr_key)
            if val is not None and str(val).strip() != "" and not (isinstance(val, float) and np.isnan(val)):
                pills_html += f'<span class="stat-pill">{attr_label} {int(val)}</span>'

        contract_html = ""
        sav = selected_player.get('Savings', '')
        pen = selected_player.get('Penalty', '')
        if sav and str(sav).strip():
            contract_html += f'<span class="stat-pill">💰 Cap Savings: {sav}</span>'
        if pen and str(pen).strip():
            contract_html += f'<span class="stat-pill">⚠️ Dead Cap: {pen}</span>'

        st.markdown(f"""
        <div class="player-spotlight">
            <div style="position:relative; z-index:1;">
                <div style="font-size:3rem; font-weight:900; color:{ovr_c};
                            text-shadow: 0 0 20px {ovr_c}40;">{ovr_val}</div>
                <div style="font-size:0.8rem; color:#64748b; text-transform:uppercase;
                            letter-spacing:2px;">OVERALL</div>
                <div style="font-size:1.6rem; font-weight:700; color:#f1f5f9;
                            margin-top:8px;">{selected_player['Name']}</div>
                <div style="margin-top:4px;">
                    <span style="background:{dev_c}20; color:{dev_c}; padding:4px 12px;
                                border-radius:20px; font-size:0.8rem; font-weight:600;
                                border: 1px solid {dev_c}50;">
                        {selected_player.get('Dev', 'Normal')}
                    </span>
                    <span style="color:#94a3b8; margin:0 8px;">·</span>
                    <span style="color:#cbd5e1;">{selected_player['Pos']}</span>
                    <span style="color:#94a3b8; margin:0 8px;">·</span>
                    <span style="color:#cbd5e1;">Age {int(selected_player.get('Age', 0))}</span>
                </div>
                <div style="margin-top:12px;">{pills_html}</div>
                <div style="margin-top:6px;">{contract_html}</div>
                <div style="margin-top:16px; font-size:1.8rem; font-weight:800;
                            background: linear-gradient(90deg, #6366f1, #10b981);
                            -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    {player_value:,.0f}
                    <span style="font-size:0.7rem; -webkit-text-fill-color: #64748b;
                                font-weight:400;"> TRADE VALUE</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Radar Chart — Physical Attributes ──
        radar_attrs = []
        radar_vals = []
        for attr_key, attr_label in [("SPD", "Speed"), ("ACC", "Accel"),
                                     ("AGI", "Agility"), ("COD", "CoD"),
                                     ("STR", "Strength"), ("AWR", "Aware")]:
            val = selected_player.get(attr_key)
            if val is not None and str(val).strip() != "" and not (isinstance(val, float) and np.isnan(val)):
                radar_attrs.append(attr_label)
                radar_vals.append(int(val))

        if len(radar_attrs) >= 3:
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(
                r=radar_vals + [radar_vals[0]],
                theta=radar_attrs + [radar_attrs[0]],
                fill='toself',
                fillcolor='rgba(99, 102, 241, 0.2)',
                line=dict(color='#6366f1', width=2),
                marker=dict(size=6, color='#a5b4fc'),
                name=selected_player['Name'],
            ))
            fig_radar.update_layout(
                polar=dict(
                    bgcolor='rgba(0,0,0,0)',
                    radialaxis=dict(visible=True, range=[40, 100],
                                    gridcolor='rgba(148,163,184,0.15)',
                                    tickfont=dict(size=9, color='#64748b')),
                    angularaxis=dict(gridcolor='rgba(148,163,184,0.15)',
                                     tickfont=dict(size=11, color='#cbd5e1')),
                ),
                showlegend=False,
                margin=dict(l=40, r=40, t=30, b=30),
                height=280,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig_radar, use_container_width=True)
        else:
            st.caption(
                "📊 _Radar chart available when SPD/ACC/AGI data is filled in._")

        # ── Interested Teams ──
        st.markdown('<div class="section-glow"></div>', unsafe_allow_html=True)
        st.markdown("#### 🎯 Interested Teams")
        partners = find_trade_partners(selected_player, user_team=MY_TEAM)
        for p in partners:
            fit_badge = ' <span style="color:#10b981; font-size:0.75rem;">✅ SCHEME FIT</span>' if p[
                "scheme_fit"] else ""
            interest = p["interest"]
            bar_color = "#10b981" if interest >= 70 else "#f59e0b" if interest >= 40 else "#ef4444"

            st.markdown(f"""
            <div class="trade-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:1.1rem; font-weight:700; color:#f1f5f9;">{p['team']}</span>
                    <span style="color:{bar_color}; font-weight:700;">{interest}%{fit_badge}</span>
                </div>
                <div class="interest-bar">
                    <div class="interest-fill" style="width:{interest}%; background: linear-gradient(90deg, {bar_color}, {bar_color}aa);"></div>
                </div>
                <div style="color:#94a3b8; font-size:0.85rem; margin-bottom:4px;">↳ {p['reason']}</div>
                <div style="color:#cbd5e1; font-size:0.9rem;">Best offer: <strong>{p['best_offer_name']}</strong>
                    <span style="color:#64748b;">({p['best_offer_pos']}, {p['best_offer_ovr']} OVR)</span></div>
            </div>
            """, unsafe_allow_html=True)

    # ── RIGHT COLUMN — Trade Evaluator ──
    with tmcol2:
        st.markdown("#### ⚖️ Trade Evaluator")
        st.markdown('<p style="color:#94a3b8;">Build a trade and see if the CPU accepts.</p>',
                    unsafe_allow_html=True)

        # Offered player(s) — user's side
        st.markdown('<div class="trade-card">', unsafe_allow_html=True)
        st.markdown("**🟢 You Send:**")
        offer_names = st.multiselect(
            "Players to offer:",
            user_roster["Name"].tolist(),
            default=[selected_player_name],
            key="trade_offer_select",
        )
        offered = [
            user_roster[user_roster["Name"] == n].iloc[0].to_dict()
            for n in offer_names
            if n in user_roster["Name"].values
        ]
        st.markdown('</div>', unsafe_allow_html=True)

        # Requested player(s) — CPU side
        st.markdown('<div class="trade-card">', unsafe_allow_html=True)
        st.markdown("**🔴 You Receive:**")
        cpu_team = st.selectbox(
            "From team:", [
                t for t in TRADE_ROSTERS["Team"].unique() if t != MY_TEAM],
            key="trade_cpu_team",
        )
        cpu_roster = TRADE_ROSTERS[TRADE_ROSTERS["Team"] == cpu_team]
        request_names = st.multiselect(
            "Players to request:",
            cpu_roster["Name"].tolist(),
            key="trade_request_select",
        )
        requested = [
            cpu_roster[cpu_roster["Name"] == n].iloc[0].to_dict()
            for n in request_names
            if n in cpu_roster["Name"].values
        ]
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("📋 Evaluate Trade", key="eval_trade_btn", use_container_width=True):
            if not offered or not requested:
                st.warning("Select at least one player on each side.")
            else:
                result = evaluate_trade(offered, requested)

                # Verdict badge
                if "ACCEPTED" in result['verdict']:
                    badge_class = "verdict-accept"
                elif "LEAN" in result['verdict']:
                    badge_class = "verdict-lean"
                else:
                    badge_class = "verdict-decline"

                st.markdown(f'<div class="{badge_class}">{result["verdict"]}</div>',
                            unsafe_allow_html=True)
                st.markdown("")

                # Trade value comparison — horizontal bar chart
                fig_compare = go.Figure()
                fig_compare.add_trace(go.Bar(
                    y=["Their Side", "Your Offer"],
                    x=[result["requested_value"], result["offered_value"]],
                    orientation='h',
                    marker=dict(
                        color=['#ef4444', '#10b981'],
                        line=dict(width=0),
                    ),
                    text=[f"{result['requested_value']:,.0f}",
                          f"{result['offered_value']:,.0f}"],
                    textposition='inside',
                    textfont=dict(size=14, color='white',
                                  family='Arial Black'),
                ))
                fig_compare.update_layout(
                    height=140,
                    margin=dict(l=0, r=20, t=10, b=10),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(visible=False),
                    yaxis=dict(tickfont=dict(size=12, color='#cbd5e1'),
                               gridcolor='rgba(0,0,0,0)'),
                    bargap=0.35,
                )
                st.plotly_chart(fig_compare, use_container_width=True)

                # Diff metric
                diff = result['diff']
                diff_label = f"+{diff:,.0f} in your favor" if diff > 0 else f"{diff:,.0f} gap to close"
                diff_color = "#10b981" if diff >= 0 else "#f59e0b"
                st.markdown(f'<div style="text-align:center; color:{diff_color}; '
                            f'font-weight:700; font-size:1.1rem;">'
                            f'{diff_label}</div>', unsafe_allow_html=True)

                if result["counter_offer"]:
                    st.markdown("")
                    st.markdown(f"""
                    <div class="trade-card" style="border-color: rgba(245,158,11,0.4);">
                        <div style="color:#f59e0b; font-weight:700; margin-bottom:6px;">💡 GM Suggestion</div>
                        <div style="color:#e2e8f0;">{result['counter_offer']}</div>
                    </div>
                    """, unsafe_allow_html=True)

# ── TAB 4: Dynasty ──
with tabs[3]:
    st.subheader("🏛️ Dynasty — Franchise Legacy")

    history = load_history()

    # Timeline visualization
    st.markdown("#### 📅 Franchise Timeline")
    if history:
        hist_df = pd.DataFrame(history)
        fig_timeline = px.scatter(
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
        fig_timeline.update_traces(marker=dict(
            line=dict(width=2, color="white")))
        fig_timeline.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig_timeline, use_container_width=True)

        # Season detail cards
        st.markdown("#### 📜 The Chronicles")
        for season in reversed(history):
            era_label = season.get("era", "Unknown Era")
            trophy = " 🏆" if "Champion" in season.get(
                "playoff_result", "") else ""
            with st.expander(f"Season {season['season']} — {era_label}{trophy}"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Record", season.get("record", "N/A"))
                    st.metric("Playoff Result", season.get(
                        "playoff_result", "N/A"))
                with c2:
                    st.metric("MVP", season.get("mvp", "N/A"))
                    st.caption(season.get("mvp_stats", ""))
                with c3:
                    st.metric(
                        "Top Rusher", f"{season.get('top_rusher', 'N/A')} ({season.get('rush_yards', 0)} yds)")
                    st.metric(
                        "Top Receiver", f"{season.get('top_receiver', 'N/A')} ({season.get('rec_yards', 0)} yds)")
                if season.get("notes"):
                    st.caption(f"📝 {season['notes']}")
    else:
        st.info("No dynasty history yet. Archive your first season below!")

    st.markdown("---")

    # Career Leaderboard
    st.markdown("#### 📊 Career Leaderboard")
    leaders_df = get_career_leaders(history)
    if not leaders_df.empty:
        st.dataframe(
            leaders_df.style.format({
                "Rush Yds": "{:,.0f}",
                "Rec Yds": "{:,.0f}",
                "Total Yds": "{:,.0f}",
            }),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No career leaders data available yet.")

    st.markdown("---")

    # Archive new season form
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
            new_mvp = st.text_input(
                "MVP Player", placeholder="e.g. Jordan Love")
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

            season_data = {
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
            }
            archive_season(season_data, history)
            st.success(f"✅ Season {new_season} archived under \"{new_era}\"!")
            st.rerun()

# ── TAB 5: Roster Explorer ──
with tabs[4]:
    st.subheader("📋 Roster Explorer")

    rcol1, rcol2 = st.columns([1, 3])

    with rcol1:
        selected_team = MY_TEAM
        st.info(f"Showing: **{selected_team}**")
        selected_group = st.selectbox(
            "Position Group:", POSITION_GROUPS, key="roster_group_select")

        summary = get_team_summary(selected_team, AI_GM_EXTRA)
        st.markdown("---")
        st.metric("Players", summary["count"])
        st.metric("Avg OVR", summary["avg_ovr"])
        st.metric("Avg Age", summary["avg_age"])
        st.markdown(
            f"⭐ **Best Player:** {summary.get('best_player', 'N/A')} ({summary.get('best_ovr', 'N/A')} OVR)")

    with rcol2:
        roster_df = get_roster(selected_team, selected_group, AI_GM_EXTRA)
        if roster_df.empty:
            st.info(f"No players found for {selected_team} — {selected_group}")
        else:
            # Add tier column and sort by OVR
            roster_display = roster_df[[
                "Name", "Pos", "OVR", "Age", "Dev"]].copy()
            roster_display["Tier"] = roster_display["OVR"].apply(ovr_label)
            roster_display = roster_display.sort_values(
                "OVR", ascending=False).reset_index(drop=True)

            # Style the dataframe with OVR color coding
            def style_ovr(val):
                color = ovr_color(val)
                return f"color: {color}; font-weight: bold"

            def style_tier(val):
                colors = {
                    "Elite": "#00e676",
                    "Great": "#2196f3",
                    "Average": "#ffc107",
                    "Developing": "#ff5252",
                }
                return f"color: {colors.get(val, 'white')}; font-weight: bold"

            styled = roster_display.style.map(
                style_ovr, subset=["OVR"]
            ).map(
                style_tier, subset=["Tier"]
            )

            st.dataframe(styled, hide_index=True,
                         use_container_width=True, height=500)

            # Position breakdown chart
            st.markdown("#### Position Breakdown")
            pos_counts = roster_df["Pos"].value_counts().reset_index()
            pos_counts.columns = ["Position", "Count"]
            fig_pos = px.bar(
                pos_counts,
                x="Position",
                y="Count",
                template="plotly_dark",
                color="Count",
                color_continuous_scale="Viridis",
            )
            fig_pos.update_layout(showlegend=False)
            st.plotly_chart(fig_pos, use_container_width=True)

    # ── Trade Value Leaderboard ──
    st.markdown("---")
    st.markdown("#### 💎 Trade Value Leaderboard")
    st.caption(
        "Players ranked by trade value — factors in OVR, age, position, dev trait, contract, and athleticism.")

    all_gb = get_roster(selected_team, "All", AI_GM_EXTRA)
    if not all_gb.empty:
        tv_rows = []
        for _, p in all_gb.iterrows():
            tv = get_trade_value(p.to_dict())
            tv_rows.append({
                "Name": p["Name"], "Pos": p["Pos"], "OVR": int(p["OVR"]),
                "Age": int(p["Age"]), "Dev": p.get("Dev", "Normal"),
                "Trade Value": tv,
            })
        tv_df = pd.DataFrame(tv_rows).sort_values(
            "Trade Value", ascending=False).reset_index(drop=True)
        tv_df.index += 1
        tv_df.index.name = "Rank"

        def style_tv(val):
            if val >= 700:
                return "color: #00e676; font-weight: bold"
            elif val >= 500:
                return "color: #2196f3; font-weight: bold"
            elif val >= 350:
                return "color: #ffc107; font-weight: bold"
            return "color: #ff5252; font-weight: bold"

        styled_tv = tv_df.style.map(style_tv, subset=["Trade Value"]).map(
            style_ovr, subset=["OVR"]).format({"Trade Value": "{:.1f}"})

        st.dataframe(styled_tv, use_container_width=True, height=450)

    # ── Position Group Grades ──
    st.markdown("---")
    st.markdown("#### 📊 Position Group Grades")
    grades = get_position_grades(selected_team, AI_GM_EXTRA)
    if grades:
        grade_cols = st.columns(4)
        for i, g in enumerate(grades):
            with grade_cols[i % 4]:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, rgba(30,30,60,0.9), rgba(50,50,80,0.7));
                    border: 1px solid {g['color']}40; border-radius: 14px; padding: 1rem;
                    text-align: center; margin-bottom: 0.8rem;">
                    <div style="font-size: 2rem; font-weight: 900; color: {g['color']};">{g['grade']}</div>
                    <div style="font-size: 1.1rem; font-weight: 700; color: white;">{g['pos']}</div>
                    <div style="font-size: 0.8rem; color: #aaa;">{g['count']} players · {g['avg_ovr']} avg</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No position data available.")

    # ── Cap Overview Widget ──
    st.markdown("---")
    st.markdown("#### 💰 Cap Overview")
    cap = get_cap_summary(selected_team, AI_GM_EXTRA)
    if cap["players"]:
        cap_c1, cap_c2, cap_c3 = st.columns(3)
        with cap_c1:
            st.metric("Total Cap Savings", f"${cap['total_savings']:.1f}M")
        with cap_c2:
            st.metric("Total Dead Cap", f"${cap['total_penalty']:.1f}M",
                      delta=f"-${cap['total_penalty']:.1f}M", delta_color="inverse")
        with cap_c3:
            net = cap['total_savings'] - cap['total_penalty']
            st.metric("Net Cap Position", f"${net:+.1f}M",
                      delta="Healthy" if net > 0 else "Tight",
                      delta_color="normal" if net > 0 else "inverse")

        st.markdown("##### 🔴 Top 5 Dead Cap Hits")
        top_dead = [p for p in cap["players"] if p["Penalty"] > 0][:5]
        if top_dead:
            dead_df = pd.DataFrame(top_dead)
            dead_df["Penalty"] = dead_df["Penalty"].apply(
                lambda x: f"${x:.2f}M")
            dead_df["Savings"] = dead_df["Savings"].apply(
                lambda x: f"${x:.2f}M")
            st.dataframe(dead_df, hide_index=True, use_container_width=True)
        else:
            st.info("No dead cap obligations found.")
    else:
        st.info("No contract data available.")

    # ── Cut or Keep Analyzer ──
    st.markdown("---")
    st.markdown("#### ✂️ Cut or Keep Analyzer")
    verdicts = analyze_roster(selected_team, AI_GM_EXTRA)
    if verdicts:
        # Summary counts
        n_keep = sum(1 for v in verdicts if v["Verdict"] == "KEEP")
        n_trade = sum(1 for v in verdicts if v["Verdict"] == "TRADE")
        n_cut = sum(1 for v in verdicts if v["Verdict"] == "CUT")
        ck1, ck2, ck3 = st.columns(3)
        with ck1:
            st.metric("✅ Keep", n_keep)
        with ck2:
            st.metric("🟡 Trade Candidates", n_trade)
        with ck3:
            st.metric("🔴 Cut Candidates", n_cut)

        verdict_colors = {"KEEP": "#00e676",
                          "TRADE": "#ffc107", "CUT": "#ff5252"}
        verdict_icons = {"KEEP": "✅", "TRADE": "📦", "CUT": "✂️"}
        ck_cols = st.columns(3)
        for i, v in enumerate(verdicts):
            with ck_cols[i % 3]:
                vc = verdict_colors[v["Verdict"]]
                vi = verdict_icons[v["Verdict"]]
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
    else:
        st.info("No roster data for analysis.")

    # ── Depth Chart Visualization ──
    st.markdown("---")
    st.markdown("#### 📋 Depth Chart")
    dc_side = st.radio("Unit", ["Offense", "Defense"], horizontal=True,
                       key="dc_unit")

    _OFF_POSITIONS = ["QB", "HB", "WR", "TE", "LT", "LG", "C", "RG", "RT"]
    _DEF_POSITIONS = ["EDGE", "DT", "MLB", "OLB", "CB", "SS", "FS"]
    dc_positions = _OFF_POSITIONS if dc_side == "Offense" else _DEF_POSITIONS

    full_roster = get_roster(selected_team, "All", AI_GM_EXTRA)
    dc_cols = st.columns(len(dc_positions))
    for i, pos in enumerate(dc_positions):
        with dc_cols[i]:
            pos_players = full_roster[full_roster["Pos"] == pos].sort_values(
                "OVR", ascending=False)
            st.markdown(f"<div style='text-align:center; font-weight:800; "
                        f"color: #6366f1; margin-bottom:4px;'>{pos}</div>",
                        unsafe_allow_html=True)
            for j, (_, p) in enumerate(pos_players.iterrows()):
                ovr = int(p['OVR'])
                oc = ovr_color(ovr)
                cls = 'dc-starter' if j == 0 else 'dc-backup'
                dev_icon = {'Superstar X': '⭐', 'Superstar': '🌟',
                            'Star': '✨', 'Normal': ''}.get(
                    str(p.get('Dev', 'Normal')), '')
                st.markdown(f"""
                <div class="dc-card {cls}">
                    <div style="font-weight:700; color:white; font-size:0.85rem;">
                        {p['Name'].split('.')[-1].strip() if '.' in str(p['Name']) else p['Name']}
                    </div>
                    <div style="font-size:1.4rem; font-weight:900; color:{oc};">
                        {ovr} {dev_icon}
                    </div>
                    <div style="font-size:0.7rem; color:#aaa;">Age {int(p['Age'])}</div>
                </div>
                """, unsafe_allow_html=True)
            if pos_players.empty:
                st.markdown("<div class='dc-card' style='color:#666;'>Empty</div>",
                            unsafe_allow_html=True)

# ── TAB 6: Season Awards ──
with tabs[5]:
    st.subheader("🏆 Season Awards")
    st.markdown("Auto-generated awards based on your current roster data.")

    roster_full = get_roster(MY_TEAM, "All")
    if not roster_full.empty:
        # Compute trade values for all players
        award_data = []
        for _, row in roster_full.iterrows():
            tv = get_trade_value(row.to_dict())
            award_data.append({**row.to_dict(), "TV": tv})
        award_df = pd.DataFrame(award_data)

        # MVP: highest trade value
        mvp = award_df.loc[award_df["TV"].idxmax()]
        # DPOY: highest OVR defensive player
        def_df = award_df[award_df["Pos"].isin(
            ["EDGE", "DT", "MLB", "OLB", "CB", "FS", "SS"])]
        dpoy = def_df.loc[def_df["OVR"].idxmax()] if not def_df.empty else None
        # OROY/DROY: best player age <= 22
        young = award_df[award_df["Age"] <= 22]
        roy = young.loc[young["OVR"].idxmax()] if not young.empty else None
        # Iron Man: oldest player above 80 OVR
        vet = award_df[(award_df["Age"] >= 29) & (award_df["OVR"] >= 80)]
        iron = vet.loc[vet["Age"].idxmax()] if not vet.empty else None
        # Best Contract: highest OVR with lowest penalty
        award_df["_pen"] = award_df.get("Penalty", pd.Series([0]*len(award_df))).apply(
            lambda x: float(str(x).replace("$", "").replace(
                "M", "").replace("K", "").strip() or 0)
        )
        has_pen = award_df[award_df["_pen"] > 0]
        if not has_pen.empty:
            has_pen = has_pen.copy()
            has_pen["value_ratio"] = has_pen["OVR"] / \
                has_pen["_pen"].clip(lower=0.1)
            best_contract = has_pen.loc[has_pen["value_ratio"].idxmax()]
        else:
            best_contract = None

        awards = [
            ("🏆 MVP", mvp, "#FFD700", "Highest trade value on the roster"),
            ("🛡️ DPOY", dpoy, "#6366f1", "Highest-rated defensive player"),
            ("⭐ ROY", roy, "#10b981", "Best player age 22 or under"),
            ("💪 Iron Man", iron, "#f59e0b", "Oldest player above 80 OVR"),
            ("💰 Best Contract", best_contract, "#06b6d4", "Best OVR-to-cap ratio"),
        ]

        award_cols = st.columns(len(awards))
        for i, (title, player, color, desc) in enumerate(awards):
            with award_cols[i]:
                if player is not None:
                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(25,25,55,0.95), rgba(45,45,75,0.8));
                        border: 2px solid {color}; border-radius: 16px; padding: 1.2rem;
                        text-align: center;">
                        <div style="font-size: 2.5rem;">{title.split(' ')[0]}</div>
                        <div style="font-size: 0.9rem; font-weight: 800; color: {color};
                            margin: 0.3rem 0;">{title.split(' ', 1)[1]}</div>
                        <div style="font-size: 1.1rem; font-weight: 700; color: white;">
                            {player['Name']}</div>
                        <div style="color: #aaa; font-size: 0.85rem;">
                            {player['Pos']} · {int(player['OVR'])} OVR · Age {int(player['Age'])}</div>
                        <div style="color: #666; font-size: 0.7rem; margin-top: 0.4rem;">{desc}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: rgba(25,25,55,0.5); border: 1px solid #333;
                        border-radius: 16px; padding: 1.2rem; text-align: center; color: #666;">
                        <div style="font-size: 2.5rem;">{title.split(' ')[0]}</div>
                        <div>{title.split(' ', 1)[1]}</div>
                        <div style="font-size: 0.8rem;">No eligible players</div>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.info("No roster data available for awards.")

# ── TAB 7: Coach DNA ──
with tabs[6]:
    st.subheader("🎯 Head Coach DNA Profile")
    st.markdown(
        "Your coaching identity, computed from your franchise game data.")

    if ("Pass_Yards" in df.columns and "Rush_Yards" in df.columns
            and "Result" in df.columns and len(df) >= 3):

        total_pass = df["Pass_Yards"].sum()
        total_rush = df["Rush_Yards"].sum()
        total_yds = total_pass + total_rush
        pass_pct = total_pass / max(total_yds, 1) * 100
        rush_pct = 100 - pass_pct

        wins = (df["Result"] == "WIN").sum()
        win_pct = wins / len(df) * 100
        avg_pf = df["Points_For"].mean() if "Points_For" in df.columns else 0
        avg_pa = df["Points_Against"].mean(
        ) if "Points_Against" in df.columns else 0
        avg_to = df["Turnovers"].mean() if "Turnovers" in df.columns else 0
        avg_tak = df["Takeaways"].mean() if "Takeaways" in df.columns else 0
        avg_sacks = df["Sacks_For"].mean() if "Sacks_For" in df.columns else 0

        # Compute 0–100 axes for radar
        passing = min(pass_pct * 1.2, 100)
        rushing = min(rush_pct * 1.5, 100)
        aggression = min(avg_pf / 0.45, 100)  # 45 PPG = 100
        ball_security = max(0, 100 - avg_to * 40)  # 0 TO = 100, 2.5 TO = 0
        def_intensity = min((avg_sacks * 15 + avg_tak * 20), 100)

        # Determine archetype
        if pass_pct > 60 and aggression > 65:
            archetype = "🌩️ Aggressive Air Raid"
        elif rush_pct > 45 and ball_security > 70:
            archetype = "🗿 Conservative Ground & Pound"
        elif pass_pct > 55 and ball_security > 60:
            archetype = "🎯 West Coast Tactician"
        elif def_intensity > 70:
            archetype = "🛡️ Defensive Mastermind"
        elif aggression > 70 and ball_security < 50:
            archetype = "🎰 Gunslinger Gambler"
        else:
            archetype = "⚖️ Balanced Strategist"

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(25,25,55,0.95), rgba(45,45,75,0.8));
            border: 1px solid rgba(99,102,241,0.3); border-radius: 20px;
            padding: 1.5rem; text-align: center; margin-bottom: 1rem;">
            <div style="font-size: 2rem; font-weight: 900; color: #6366f1;">{archetype}</div>
            <div style="color: #aaa; margin-top: 0.3rem;">
                {win_pct:.0f}% Win Rate · {avg_pf:.1f} PPG · {pass_pct:.0f}/{rush_pct:.0f} Pass/Rush Split</div>
        </div>
        """, unsafe_allow_html=True)

        # Radar chart
        categories = ["Passing", "Rushing", "Aggression",
                      "Ball Security", "Def Intensity"]
        values = [passing, rushing, aggression, ball_security, def_intensity]

        fig_dna = go.Figure()
        fig_dna.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            fillcolor="rgba(99,102,241,0.2)",
            line=dict(color="#6366f1", width=2),
            name="Your DNA",
        ))
        fig_dna.update_layout(
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
        st.plotly_chart(fig_dna, use_container_width=True)

        # Stat breakdown
        dna1, dna2, dna3, dna4, dna5 = st.columns(5)
        with dna1:
            st.metric("Pass %", f"{pass_pct:.0f}%")
        with dna2:
            st.metric("Rush %", f"{rush_pct:.0f}%")
        with dna3:
            st.metric("Avg TO/G", f"{avg_to:.1f}")
        with dna4:
            st.metric("Avg Takeaways/G", f"{avg_tak:.1f}")
        with dna5:
            st.metric("Avg Sacks/G", f"{avg_sacks:.1f}")
    else:
        st.warning(
            "Need at least 3 games with Pass/Rush data for Coach DNA analysis.")

# ── TAB 8: Progression Tracker ──
with tabs[7]:
    st.subheader("📈 Player Progression Tracker")
    st.markdown("Snapshot your roster OVRs over time to track development.")

    # Snapshot controls
    snap_c1, snap_c2, snap_c3 = st.columns([1, 1, 2])
    with snap_c1:
        snap_season = st.number_input("Season", min_value=1, max_value=30,
                                      value=1, key="snap_season")
    with snap_c2:
        snap_week = st.number_input("Week", min_value=1, max_value=22,
                                    value=1, key="snap_week")
    with snap_c3:
        if st.button("📸 Save Current OVR Snapshot", type="primary"):
            count = snapshot_roster(MY_TEAM, snap_season, snap_week)
            st.success(
                f"Saved {count} player OVRs for Season {snap_season}, Week {snap_week}!")

    # Show movers
    movers = get_movers(MY_TEAM)
    if movers["gainers"] or movers["losers"]:
        mov1, mov2 = st.columns(2)
        with mov1:
            st.markdown("##### 📈 Biggest Gainers")
            for g in movers["gainers"]:
                st.markdown(f"""
                <div style="background: rgba(0,230,118,0.1); border-left: 3px solid #00e676;
                    border-radius: 8px; padding: 0.5rem 0.8rem; margin-bottom: 0.4rem;">
                    <span style="font-weight:700; color:white;">{g['Name']}</span>
                    <span style="color:#aaa;"> {g['Pos']}</span>
                    <span style="float:right; color:#00e676; font-weight:800;">+{g['Delta']} ({g['Start_OVR']}→{g['Current_OVR']})</span>
                </div>
                """, unsafe_allow_html=True)
        with mov2:
            st.markdown("##### 📉 Biggest Declines")
            for loser in movers["losers"]:
                st.markdown(f"""
                <div style="background: rgba(255,82,82,0.1); border-left: 3px solid #ff5252;
                    border-radius: 8px; padding: 0.5rem 0.8rem; margin-bottom: 0.4rem;">
                    <span style="font-weight:700; color:white;">{loser['Name']}</span>
                    <span style="color:#aaa;"> {loser['Pos']}</span>
                    <span style="float:right; color:#ff5252; font-weight:800;">{loser['Delta']} ({loser['Start_OVR']}→{loser['Current_OVR']})</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("💡 Save at least 2 snapshots at different weeks to see progression data. "
                "Click the button above to save your first snapshot!")

    # Show full progression log
    prog_log = get_progression(MY_TEAM)
    if not prog_log.empty:
        st.markdown("##### 📚 Full Progression Log")
        st.dataframe(prog_log, hide_index=True,
                     use_container_width=True, height=300)

# ── TAB 9: Raw Data ──
with tabs[8]:
    st.subheader("Historical Game Logs")
    st.dataframe(df)

# ── TAB 10: AI GM Assistant — plug in new players dynamically ──
with tabs[9]:
    st.markdown('<div style="text-align:center;"><h2 style="'
                'background: linear-gradient(90deg, #6366f1, #10b981);'
                '-webkit-background-clip: text; -webkit-text-fill-color: transparent;'
                'font-size: 2rem; margin-bottom: 0;">'
                '🤖 AI GM Assistant</h2>'
                '<p style="color:#94a3b8; font-size:0.95rem;">'
                'Scout a draft pick, UDFA, or trade target — plug them into the '
                f'{MY_TEAM} roster and get an instant AI grade.</p></div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-glow"></div>', unsafe_allow_html=True)

    if ai_client.is_available():
        st.markdown('<span style="background:#00e67620; color:#00e676; '
                    'padding:3px 10px; border-radius:20px; font-size:0.78rem; '
                    'font-weight:700; border:1px solid #00e67650;">'
                    '🟢 Live Claude scouting narratives</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span style="background:#ffffff10; color:#94a3b8; '
                    'padding:3px 10px; border-radius:20px; font-size:0.78rem; '
                    'font-weight:600; border:1px solid #ffffff20;">'
                    '⚪ Heuristic scouting (set ANTHROPIC_API_KEY for live Claude writeups)</span>',
                    unsafe_allow_html=True)

    if "ai_gm_log" not in st.session_state:
        st.session_state.ai_gm_log = []
    if "ai_gm_form_version" not in st.session_state:
        st.session_state.ai_gm_form_version = 0

    gm_col1, gm_col2 = st.columns([1, 1], gap="large")

    # ── LEFT — Add Player Form ──
    with gm_col1:
        st.markdown("#### ➕ Scout & Add a Player")
        # Keying the form on a version counter (bumped only after a
        # successful add) resets the fields for the next entry without
        # wiping them out from under a failed validation.
        form_key = f"ai_gm_add_player_form_{st.session_state.ai_gm_form_version}"
        with st.form(form_key, clear_on_submit=False):
            f_name = st.text_input("Name", placeholder="e.g. J. Smith")
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                f_pos = st.selectbox("Position", ai_gm.SCOUTABLE_POSITIONS)
            with fc2:
                f_age = st.number_input(
                    "Age", min_value=18, max_value=45, value=22)
            with fc3:
                f_ovr = st.number_input(
                    "OVR", min_value=1, max_value=99, value=70)

            f_dev = st.selectbox("Dev Trait", ai_gm.DEV_TRAITS)

            st.caption("Physical attributes (optional — powers the AI scouting read)")
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                f_spd = st.slider("SPD", 0, 99, 80)
                f_cod = st.slider("COD", 0, 99, 80)
            with ac2:
                f_acc = st.slider("ACC", 0, 99, 80)
                f_str = st.slider("STR", 0, 99, 70)
            with ac3:
                f_agi = st.slider("AGI", 0, 99, 80)
                f_awr = st.slider("AWR", 0, 99, 70)

            cc1, cc2 = st.columns(2)
            with cc1:
                f_savings = st.text_input("Cap Savings", value="$0")
            with cc2:
                f_penalty = st.text_input("Dead Cap Penalty", value="$0")

            f_persist = st.checkbox(
                "💾 Save to roster CSV (persists across restarts)", value=False)

            submitted = st.form_submit_button(
                "🔮 Scout & Add to Roster", use_container_width=True)

        if submitted:
            new_player = {
                "Name": f_name, "Pos": f_pos, "Age": f_age, "OVR": f_ovr,
                "Dev": f_dev, "SPD": f_spd, "ACC": f_acc, "AGI": f_agi,
                "COD": f_cod, "STR": f_str, "AWR": f_awr,
                "Savings": f_savings, "Penalty": f_penalty,
            }
            result = ai_gm.add_player(new_player, MY_TEAM)
            if not result["ok"]:
                for err in result["errors"]:
                    st.error(err)
            else:
                report = ai_gm.scout_player(
                    result["player"], MY_TEAM, AI_GM_EXTRA)

                # The verdict/grade/trade-value above are always the
                # deterministic heuristic output. If a Claude API key is
                # configured, ask it to rewrite just the narrative blurb
                # grounded in those already-computed facts; otherwise the
                # templated heuristic blurb stands as-is.
                if ai_client.is_available():
                    with st.spinner("Consulting AI GM..."):
                        ai_blurb = ai_client.generate_scouting_narrative(
                            result["player"], report, MY_TEAM)
                    if ai_blurb:
                        report["blurb"] = ai_blurb
                        report["ai_generated"] = True
                    else:
                        report["ai_generated"] = False
                        st.warning(
                            "Claude request failed — showing heuristic scouting report instead.")
                else:
                    report["ai_generated"] = False

                st.session_state.ai_gm_players.append(result["player"])
                st.session_state.ai_gm_log.insert(0, report)
                if f_persist:
                    ai_gm.persist_roster(MY_TEAM, st.session_state.ai_gm_players)
                st.session_state.ai_gm_form_version += 1
                st.success(
                    f"✅ **{result['player']['Name']}** added to the {MY_TEAM} roster.")
                st.rerun()

        st.markdown("---")
        st.markdown("#### 🧭 Positional Needs Board")
        st.caption("AI-computed depth + quality grade per position — use this to decide who to scout next.")
        needs = ai_gm.positional_needs(MY_TEAM, AI_GM_EXTRA)
        need_cols = st.columns(4)
        for i, n in enumerate(needs):
            with need_cols[i % 4]:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, rgba(30,30,60,0.9), rgba(50,50,80,0.7));
                    border: 1px solid {n['color']}40; border-left: 4px solid {n['color']};
                    border-radius: 12px; padding: 0.7rem; margin-bottom: 0.6rem; text-align:center;">
                    <div style="font-weight:800; color:white;">{n['pos']}</div>
                    <div style="color:{n['color']}; font-weight:700; font-size:0.85rem;">{n['level']}</div>
                    <div style="color:#888; font-size:0.72rem;">{n['count']} plyr · {n['avg_ovr']:.0f} avg</div>
                </div>
                """, unsafe_allow_html=True)

    # ── RIGHT — Scouting Report Feed ──
    with gm_col2:
        st.markdown("#### 📋 AI Scouting Reports")
        if not st.session_state.ai_gm_log:
            st.info("Add a player on the left to generate an AI scouting report.")
        else:
            for idx, rep in enumerate(st.session_state.ai_gm_log):
                vc = rep["verdict_color"]
                source_badge = ('<span style="color:#a78bfa; font-size:0.7rem; font-weight:700;">✨ Claude</span>'
                                if rep.get("ai_generated") else
                                '<span style="color:#64748b; font-size:0.7rem;">⚙️ Heuristic</span>')
                st.markdown(f"""
                <div class="trade-card" style="border-left: 4px solid {vc};">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.15rem; font-weight:800; color:#f1f5f9;">
                            {rep['Name']} <span style="color:#94a3b8; font-weight:500; font-size:0.85rem;">
                            {rep['Pos']} · {rep['Age']}yo · {rep['OVR']} OVR</span>
                        </span>
                        <span style="background:{vc}; color:#000; font-weight:800; padding:2px 10px;
                            border-radius:8px; font-size:0.75rem; white-space:nowrap;">{rep['verdict']}</span>
                    </div>
                    <div style="color:#cbd5e1; font-size:0.85rem; margin-top:8px; line-height:1.5;">{rep['blurb']}</div>
                    <div style="margin-top:6px;">{source_badge}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"🗑️ Remove {rep['Name']}", key=f"ai_gm_remove_{rep['_id']}"):
                    st.session_state.ai_gm_players = ai_gm.remove_from_list(
                        st.session_state.ai_gm_players, rep["_id"])
                    st.session_state.ai_gm_log = [
                        r for r in st.session_state.ai_gm_log if r["_id"] != rep["_id"]]
                    st.rerun()

    # ── Ask the AI GM — free-form chat grounded in real roster data ──
    st.markdown("---")
    st.markdown("#### 💬 Ask the AI GM")
    st.caption(
        "Ask anything about your roster, cap situation, trade targets, or "
        "needs — every answer is grounded in your actual data below, not "
        "a generic guess.")

    if "ai_gm_chat" not in st.session_state:
        st.session_state.ai_gm_chat = []
    # Stale chat referencing a different team's data would be misleading —
    # reset on team switch rather than let old answers linger.
    if st.session_state.get("ai_gm_chat_team") != MY_TEAM:
        st.session_state.ai_gm_chat = []
        st.session_state.ai_gm_chat_team = MY_TEAM

    if not ai_client.is_available():
        st.info(
            "💬 Chat requires a live Claude connection — set `ANTHROPIC_API_KEY` "
            "(env var locally, or Streamlit Cloud Settings → Secrets) to unlock it. "
            "The scouting reports above still work either way.")
    else:
        for msg in st.session_state.ai_gm_chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if st.session_state.ai_gm_chat:
            if st.button("🗑️ Clear chat", key="ai_gm_chat_clear"):
                st.session_state.ai_gm_chat = []
                st.rerun()

        if prompt := st.chat_input("e.g. Who should I trade for a pass rusher?"):
            st.session_state.ai_gm_chat.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Consulting the AI GM..."):
                    context_summary = ai_gm.build_context_summary(MY_TEAM, AI_GM_EXTRA)
                    # Exclude the prompt just appended — answer_gm_question
                    # takes it separately — and cap history length so the
                    # prompt doesn't grow unbounded over a long session.
                    history = st.session_state.ai_gm_chat[:-1][-12:]
                    answer = ai_client.answer_gm_question(
                        prompt, context_summary, history, MY_TEAM)
                    if answer is None:
                        answer = "Sorry — I couldn't reach Claude just now. Please try again in a moment."
                st.markdown(answer)
            st.session_state.ai_gm_chat.append({"role": "assistant", "content": answer})
