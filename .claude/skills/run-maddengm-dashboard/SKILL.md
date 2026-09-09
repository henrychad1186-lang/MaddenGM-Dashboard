---
name: run-maddengm-dashboard
description: Build, run, and drive the MaddenGM Dashboard Streamlit app. Use when asked to start the dashboard, launch the app, take a screenshot of the UI, click through its tabs (Scheme Performance, Trade Machine, Roster Explorer, etc.), or verify a change works in the running app.
---

This is a Streamlit app (`app.py` at repo root) — a single-page dashboard
with a tab strip (Scheme Performance, Wear & Tear, Trade Machine, Dynasty,
Roster Explorer, Season Awards, Coach DNA, Progression, ...). Drive it by
starting the Streamlit server, then running the headless-Chromium driver at
`.claude/skills/run-maddengm-dashboard/driver.py` against it. No `chromium-cli`
in this container — the driver is a small Playwright script instead.

All paths below are relative to the repo root.

## Prerequisites

Playwright's Python package plus its browser binaries. In this container the
Chromium binary is already present at
`/opt/pw-browsers/chromium-1194/chrome-linux/chrome` (set via
`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`) — only the pip package needs
installing:

```bash
pip install playwright
```

## Setup

```bash
pip install -r requirements.txt
```

No env vars are required to launch — the app auto-loads local sample data
under `data/` and shows a "Local Franchise Data Loaded!" banner. An
`ANTHROPIC_API_KEY` env var (or `.streamlit/secrets.toml`) enables the
optional live AI scouting narratives (`src/ai_client.py`); without it the
app falls back to deterministic blurbs and still runs fully.

## Run (agent path)

Start the server in the background and poll until it serves:

```bash
nohup streamlit run app.py --server.headless true --server.port 8501 \
  > /tmp/streamlit.log 2>&1 &
timeout 30 bash -c 'until curl -sf http://localhost:8501 >/dev/null; do sleep 1; done'
```

Then drive it — the driver loads the home page, screenshots it, and clicks
any tab labels you pass as args, screenshotting after each:

```bash
python3 .claude/skills/run-maddengm-dashboard/driver.py "Trade Machine" "Roster Explorer"
```

Screenshots land in `.claude/skills/run-maddengm-dashboard/shots/`
(`00_home.png`, `01_Trade_Machine.png`, `02_Roster_Explorer.png`, ...). The
driver prints each screenshot path, then prints any browser console errors
and exits 1 if there were any — check both, not just that the process
exited 0.

Stop the server when done:

```bash
lsof -ti:8501 -sTCP:LISTEN | xargs -r kill
```

## Run (human path)

```bash
streamlit run app.py   # opens a browser tab at http://localhost:8501; Ctrl-C to stop
```

Headless in this container that just starts the server with no browser —
use the agent path above to actually see it.

## Test

```bash
pip install pytest
python -m pytest -q
```

20 tests pass (`tests/test_roster.py`, `tests/test_roster_analyzer.py`,
`tests/test_ai_client.py`).

## Gotchas

- **`playwright install` / browser auto-download does nothing here** — the
  environment sets `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` and pre-installs
  Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`. Pass that
  path explicitly as `executable_path` (the driver already does) — the
  default `p.chromium.launch()` looks for a different revision path and
  fails with "executable doesn't exist".
- **`curl` on `/` only proves the Streamlit shell loaded**, not that the app
  rendered — the page body is a near-empty HTML shell until the client JS
  connects over websocket and Streamlit runs `app.py` server-side. Always
  drive it with the Playwright script and `wait_for_selector` on real
  content (e.g. `"text=Franchise Key Performance Indicators"`), not just a
  200 from `curl`.
- **IPv6 bind warning is harmless** — `streamlit run` logs "Could not bind
  IPv6 wildcard address :::8501; falling back to 0.0.0.0:8501" on startup in
  this container; the server still comes up fine on `localhost:8501`.
