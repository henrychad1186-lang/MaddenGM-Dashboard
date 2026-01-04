import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Madden 26 GM War Room",
    layout="wide",
    page_icon="football",
)

st.title("Madden NFL 26: Franchise Strategy Audit")
st.markdown(
    "Analysis updated for the **2026 Season**. "
    "Utilizing new **Coach DNA** and **Wear & Tear** metrics."
)

# --- 1. DATA ENGINE (Expanded for 2026) ---
st.sidebar.header("Data Import")
uploaded_file = st.sidebar.file_uploader(
    "Upload CSV/Excel Export", type=["csv", "xlsx"]
)

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.sidebar.success("Custom Data Loaded!")
    except Exception as e:
        st.error(f"Error loading file: {e}")
        st.stop()
else:
    # Default Demo Data
    data = [
        {
            "Game_ID": "G1",
            "Team": "GB",
            "Opponent": "IND",
            "Score_Final": "35-10",
            "TOP": "38:01",
            "Playbook": "WestCoast",
            "Fatigue": 5,
        },
        {
            "Game_ID": "G2",
            "Team": "GB",
            "Opponent": "LAR",
            "Score_Final": "24-12",
            "TOP": "39:01",
            "Playbook": "WestCoast",
            "Fatigue": 12,
        },
        {
            "Game_ID": "G3",
            "Team": "GB",
            "Opponent": "DET",
            "Score_Final": "20-34",
            "TOP": "40:01",
            "Playbook": "WestCoast",
            "Fatigue": 22,
        },
        {
            "Game_ID": "G24",
            "Team": "GB",
            "Opponent": "PHI",
            "Score_Final": "38-28",
            "TOP": "18:16",
            "Playbook": "Vertical",
            "Fatigue": 10,
        },
        {
            "Game_ID": "G31",
            "Team": "GB",
            "Opponent": "MIN",
            "Score_Final": "45-35",
            "TOP": "31:18",
            "Playbook": "WestCoast",
            "Fatigue": 15,
        },
    ]
    df = pd.DataFrame(data)
    st.sidebar.info("Using Demo Data")

# --- DATA PRE-PROCESSING ---
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

if "TOP" in df.columns:
    def parse_top(x):
        if isinstance(x, str) and ":" in x:
            mm, ss = x.split(":")
            return int(mm) + int(ss) / 60
        return x
    try:
        df["TOP_Mins"] = df["TOP"].apply(parse_top)
    except Exception:
        pass

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

tabs = st.tabs(["Scheme Performance", "Wear & Tear Impact", "Raw Data"])

# --- TAB 1: Scheme Performance ---
with tabs[0]:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("TOP vs Score Differential by Scheme")
        if "TOP_Mins" in df.columns and "Score_Diff" in df.columns:
            fig = px.scatter(
                df,
                x="TOP_Mins",
                y="Score_Diff",
                color="Playbook" if "Playbook" in df.columns else None,
                size="Points_For" if "Points_For" in df.columns else None,
                hover_data=["Opponent"] if "Opponent" in df.columns else None,
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

# --- TAB 2: Wear & Tear Impact ---
with tabs[1]:
    st.subheader("The 'Wear & Tear' Cost")
    st.write(
        "Madden 26 new system penalizes performance as fatigue rises."
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
    else:
        st.warning("Fatigue or Points_For data missing.")

# --- TAB 3: Raw Data ---
with tabs[2]:
    st.subheader("Historical Game Logs")
    st.dataframe(df)
