"""
Sidebar: game-log import, dashboard filters, team selector, live predictor.

This is the only place that puts data *into* the app, so it runs before
any tab renders and hands back the filtered game log and the selected
team through `AppContext`.
"""

import io
import os

import numpy as np
import pandas as pd
import streamlit as st

from src.roster import TEAMS

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_GAME_LOGS_CSV = os.path.join(_DATA_DIR, "game_logs.csv")


# ──────────────────────────────────────────────
# GAME LOG LOADING
# ──────────────────────────────────────────────

def prepare_game_log(raw_df: pd.DataFrame) -> "tuple[pd.DataFrame, list[str]]":
    """Derive Points_For/Points_Against/Score_Diff/Result/TOP_Mins.

    Returns (df, warnings) instead of calling st.warning() directly —
    this runs inside @st.cache_data functions, and a live UI call there
    only fires on a cache miss, so a persistent warning would silently
    stop reappearing on cache hits. Returning it as data lets the
    (uncached) caller display it on every rerun regardless of cache state.
    """
    df = raw_df.copy()
    warnings: list[str] = []

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
            warnings.append("Could not parse Score_Final. Ensure format is '35-10'.")
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

    return df, warnings


@st.cache_data(ttl=120, show_spinner=False)
def _load_from_url(url: str) -> "tuple[pd.DataFrame, list[str]]":
    return prepare_game_log(pd.read_csv(url))


@st.cache_data(show_spinner=False)
def _load_from_upload(file_bytes: bytes, filename: str) -> "tuple[pd.DataFrame, list[str]]":
    buffer = io.BytesIO(file_bytes)
    if filename.lower().endswith(".csv"):
        raw_df = pd.read_csv(buffer)
    else:
        raw_df = pd.read_excel(buffer)
    return prepare_game_log(raw_df)


@st.cache_data(show_spinner=False)
def _load_from_disk(path: str, modified_at: float) -> "tuple[pd.DataFrame, list[str]]":
    return prepare_game_log(pd.read_csv(path))


def _render_data_import() -> "tuple[pd.DataFrame, list[str]]":
    """Data Import expander. Returns the unfiltered log and any warnings."""
    with st.sidebar.expander("📡 Data Import", expanded=True):
        sheet_url = st.text_input(
            "Google Sheet CSV URL",
            value="",
            placeholder="Paste your published CSV link",
            help="Publish your Google Sheet (File → Share → Publish to web → CSV) "
                 "and paste the URL here.",
        )

        uploaded_file = st.file_uploader("Or upload CSV/Excel", type=["csv", "xlsx"])

        df = None  # will be set by one of the branches
        prep_warnings: list[str] = []

        if sheet_url and sheet_url.strip():
            try:
                df, prep_warnings = _load_from_url(sheet_url.strip())
                # Cache locally so it works offline next time
                try:
                    df.to_csv(_GAME_LOGS_CSV, index=False)
                except OSError:
                    pass  # read-only filesystem (e.g. Streamlit Cloud)
                st.success(f"📡 Live Sheet Synced — {len(df)} games!")
            except Exception as e:
                st.warning(f"Sheet sync failed: {e}")
                st.info("Falling back to local data.")

        if df is None and uploaded_file:
            try:
                df, prep_warnings = _load_from_upload(
                    uploaded_file.getvalue(), uploaded_file.name)
                st.success("Custom Data Loaded!")
            except Exception as e:
                st.error(f"Error loading file: {e}")
                st.stop()

        if df is None and os.path.exists(_GAME_LOGS_CSV):
            df, prep_warnings = _load_from_disk(
                _GAME_LOGS_CSV, os.path.getmtime(_GAME_LOGS_CSV))
            st.success("📊 Local Franchise Data Loaded!")

        if df is None:
            # Fallback demo data
            data = [
                {"Game_ID": "G1", "Team": "DEMO", "Opponent": "JAX",
                 "Score_Final": "34-10", "TOP": "27:45",
                 "Playbook": "WestCoast", "Fatigue": 12},
            ]
            df, prep_warnings = prepare_game_log(pd.DataFrame(data))
            st.info("Using Demo Data")

    return df, prep_warnings


def apply_filters(df: pd.DataFrame, results: "list[str]",
                  playbooks: "list[str]", games_window: str) -> pd.DataFrame:
    """Narrow a game log by result, playbook, and recency window.

    An empty selection means "nothing selected", not "no filter" — it
    yields an empty frame so the KPIs read 0 rather than silently showing
    every game the user just deselected.
    """
    filtered = df.copy()

    if "Result" in filtered.columns:
        filtered = (
            filtered[filtered["Result"].isin(results)]
            if results else filtered.iloc[0:0]
        )

    if "Playbook" in filtered.columns and playbooks is not None:
        filtered = (
            filtered[filtered["Playbook"].isin(playbooks)]
            if playbooks else filtered.iloc[0:0]
        )

    if games_window != "All Games" and not filtered.empty:
        filtered = filtered.tail(int(games_window.split(" ")[1]))

    return filtered


def _render_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Dashboard Filters expander. Returns the filtered game log."""
    all_game_count = len(df)

    with st.sidebar.expander("🎚️ Dashboard Filters", expanded=False):
        result_options = ["WIN", "LOSS"] if "Result" in df.columns else []
        selected_results = (
            st.multiselect("Results", result_options, default=result_options)
            if result_options else []
        )

        playbook_options = (
            sorted(df["Playbook"].dropna().unique().tolist())
            if "Playbook" in df.columns else []
        )
        selected_playbooks = (
            st.multiselect("Playbooks", playbook_options, default=playbook_options)
            if playbook_options else None
        )

        games_window = st.selectbox(
            "Games Window", ["All Games", "Last 4", "Last 8", "Last 12"], index=0)

        filtered = apply_filters(
            df, selected_results, selected_playbooks, games_window)
        st.caption(f"Showing {len(filtered)} of {all_game_count} games")

    return filtered


def _render_team_selector() -> str:
    st.sidebar.header("My Team")
    return st.sidebar.selectbox(
        "Select Your Franchise Team", TEAMS,
        index=TEAMS.index("GB") if "GB" in TEAMS else 0,
        key="global_team_select",
    )


def _render_win_predictor() -> None:
    with st.sidebar.expander("🧠 Coach DNA: Live Predictor", expanded=False):
        st.caption("Uses Madden 27 Real-Time Coaching AI logic.")
        user_top = st.slider("Current Time of Possession (Mins)", 0, 45, 20)
        user_fatigue = st.slider("Team Wear & Tear (%)", 0, 100, 15)

        win_prob = 1 / (1 + np.exp(-(0.1 * user_top - 0.05 * user_fatigue)))
        st.metric("Projected Win Probability", f"{win_prob * 100:.1f}%")
        st.progress(float(win_prob))


def render() -> "tuple[pd.DataFrame, str]":
    """Draw the whole sidebar. Returns (filtered game log, selected team)."""
    df, prep_warnings = _render_data_import()

    # Surfaced in the main body, not the sidebar expander, so a parsing
    # problem isn't hidden behind a collapsed section.
    for warning in prep_warnings:
        st.warning(warning)

    df = _render_filters(df)
    my_team = _render_team_selector()
    _render_win_predictor()
    return df, my_team
