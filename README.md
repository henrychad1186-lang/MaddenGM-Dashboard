# MaddenGM-Dashboard

AI-powered Madden franchise management dashboard. Track game performance, analyze your coaching DNA, manage your roster, and make smarter trades.

## Quick Start

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Installation & Launch

```bash
git clone https://github.com/henrychad1186-lang/MaddenGM-Dashboard.git
cd MaddenGM-Dashboard
pip install -r requirements.txt
streamlit run app.py
```

The app will open at `http://localhost:8501`

## Features

| Tab | What It Does |
|-----|-------------|
| 📊 **Scheme Performance** | Strategy map, scheme head-to-head breakdown, season momentum curve |
| 💪 **Wear & Tear** | Turnovers, defensive performance, rush/pass balance tracking |
| 🏈 **Trade Machine** | AI trade finder, player radar charts, deal evaluator |
| 🏛️ **Dynasty** | Season archiving, franchise timeline, career leaderboards |
| 📋 **Roster Explorer** | Position grades, depth chart, cap overview, cut-or-keep analyzer |
| 🏆 **Season Awards** | Auto-generated MVP, DPOY, ROY, Iron Man, Best Contract |
| 🎯 **Coach DNA** | Coaching archetype radar chart computed from your play style |
| 📈 **Progression** | Snapshot roster OVRs over time, track player development |
| 🗂️ **Raw Data** | Full game log table |
| 🤖 **AI GM Assistant** | Plug in a new draft pick, UDFA, or trade target and get an instant AI scouting report + roster injection |

## Data Import

Three ways to get your franchise data into the app:

1. **📡 Google Sheet Sync** — Publish your Google Sheet as CSV, paste the URL in the sidebar
2. **📤 File Upload** — Upload CSV or Excel files via the sidebar
3. **📁 Local File** — Place `game_logs.csv` in the `data/` folder

### Required Columns (game_logs.csv)

| Column | Example | Required |
|--------|---------|----------|
| `Opponent` | DET | Yes |
| `Points_For` | 35 | Yes |
| `Points_Against` | 10 | Yes |
| `Result` | W or WIN | Yes |
| `TOP` | 27:45 | Optional |
| `Playbook` | WestCoast Zone Run | Optional |
| `Pass_Yards` | 285 | Optional |
| `Rush_Yards` | 142 | Optional |
| `Turnovers` | 1 | Optional |
| `Takeaways` | 3 | Optional |
| `Sacks_For` | 4 | Optional |

### Roster Data (packers_roster.csv)

Place your roster CSV in `data/packers_roster.csv` with columns: `Name, Pos, Age, OVR, SPD, ACC, AGI, COD, STR, AWR, Team, Dev, Savings, Penalty`

## AI GM Assistant

The **🤖 AI GM Assistant** tab lets you plug new players into your franchise
on the fly — no CSV editing required:

1. Fill out the scout form (name, position, age, OVR, attributes, dev trait, contract)
2. Click **Scout & Add to Roster** — the player is validated and injected into the
   live roster immediately, showing up across Roster Explorer, Cap Overview,
   Cut/Keep Analyzer, the Depth Chart, and the Trade Machine
3. Get an instant AI-generated scouting report: grade tier, strengths/weaknesses
   from the attribute profile, positional-need context, trade value, and a
   SIGN / DEVELOP / DEPTH / PASS verdict
4. Check the **Positional Needs Board** to see which position groups are
   Critical, Moderate, or Set before you scout your next target

Additions are scoped to your browser session (they won't leak into or get
overwritten by other visitors on a shared deployment) and reset if the
session ends. Check "Save to roster CSV" to persist them to
`data/packers_roster.csv` (skipped automatically on read-only deployments
like Streamlit Cloud).

## GitHub Actions

Automated Python linting on every push. Check the [Actions tab](https://github.com/henrychad1186-lang/MaddenGM-Dashboard/actions) for build status.

## Deploy

Deploy for free on [Streamlit Community Cloud](https://share.streamlit.io):

1. Push to GitHub
2. Go to share.streamlit.io → New app
3. Select this repo → Set main file to `app.py` → Deploy
