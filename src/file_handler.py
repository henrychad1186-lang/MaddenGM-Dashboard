"""
Enhanced file upload handler for MaddenGM Dashboard.
Provides validation, preview, and sample-template generation utilities.
"""

import io
import csv
import pandas as pd


# ── Accepted file types ────────────────────────────────────────────────────────
ACCEPTED_TYPES = ["csv", "xlsx"]

# Required columns for each file type
REQUIRED_GAME_LOG_COLS = {"Game_ID", "Team", "Opponent"}
REQUIRED_ROSTER_COLS = {"Name", "Pos", "OVR"}

# Column sets for sample templates
_GAME_LOG_TEMPLATE_COLS = [
    "Game_ID", "Team", "Opponent", "Score_Final", "TOP", "Playbook", "Fatigue",
]
_ROSTER_TEMPLATE_COLS = [
    "Name", "Pos", "OVR", "Age", "Speed", "Awareness", "Contract_Years",
]


# ── Validation ────────────────────────────────────────────────────────────────

def validate_file_type(filename: str) -> tuple[bool, str]:
    """
    Return (is_valid, message).
    Checks that the file extension is one of ACCEPTED_TYPES.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ACCEPTED_TYPES:
        return False, (
            f"Unsupported file type '.{ext}'. "
            f"Please upload a {' or '.join(ACCEPTED_TYPES)} file."
        )
    return True, f"File type '.{ext}' accepted."


def validate_dataframe(df: pd.DataFrame,
                       required_cols: set) -> tuple[bool, str]:
    """
    Return (is_valid, message).
    Checks that all required columns are present.
    """
    missing = required_cols - set(df.columns)
    if missing:
        return False, (
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            f"Columns found: {', '.join(df.columns.tolist())}."
        )
    if df.empty:
        return False, "The uploaded file contains no data rows."
    return True, f"Validation passed — {len(df)} rows loaded."


# ── Loading ───────────────────────────────────────────────────────────────────

def load_uploaded_file(uploaded_file) -> tuple[pd.DataFrame | None, str]:
    """
    Load an uploaded Streamlit file object into a DataFrame.
    Returns (df, message).  df is None on failure.
    """
    valid, msg = validate_file_type(uploaded_file.name)
    if not valid:
        return None, msg

    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as exc:
        return None, f"Could not parse file: {exc}"

    if df.empty:
        return None, "The uploaded file contains no data rows."

    return df, f"✅ Loaded {len(df)} rows from '{uploaded_file.name}'."


# ── Preview ───────────────────────────────────────────────────────────────────

def get_preview(df: pd.DataFrame, n_rows: int = 5) -> pd.DataFrame:
    """Return the first *n_rows* rows for a preview display."""
    return df.head(n_rows)


# ── Sample template generation ────────────────────────────────────────────────

def _build_csv_bytes(columns: list, sample_rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in sample_rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def get_game_log_template() -> bytes:
    """Return a sample game-log CSV as bytes ready for st.download_button."""
    rows = [
        {"Game_ID": "G1", "Team": "GB", "Opponent": "CHI",
         "Score_Final": "28-17", "TOP": "32:10", "Playbook": "WestCoast",
         "Fatigue": 8},
        {"Game_ID": "G2", "Team": "GB", "Opponent": "MIN",
         "Score_Final": "21-24", "TOP": "27:45", "Playbook": "WestCoast",
         "Fatigue": 12},
    ]
    return _build_csv_bytes(_GAME_LOG_TEMPLATE_COLS, rows)


def get_roster_template() -> bytes:
    """Return a sample roster CSV as bytes ready for st.download_button."""
    rows = [
        {"Name": "Jordan Love", "Pos": "QB", "OVR": 88,
         "Age": 26, "Speed": 72, "Awareness": 80, "Contract_Years": 3},
        {"Name": "AJ Dillon", "Pos": "HB", "OVR": 78,
         "Age": 25, "Speed": 82, "Awareness": 70, "Contract_Years": 2},
    ]
    return _build_csv_bytes(_ROSTER_TEMPLATE_COLS, rows)
