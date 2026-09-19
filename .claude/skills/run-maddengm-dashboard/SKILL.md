---
name: run-maddengm-dashboard
description: Build, run, and drive the MaddenGM Dashboard Streamlit app. Use when asked to start the dashboard, launch the app, take a screenshot of the UI, click through its tabs (Home, Schemes, Trades, Dynasty, Roster, Awards, Coach DNA, Progression, Raw Data, AI GM), or verify a change works in the running app.
---

This is a Streamlit app (`app.py` at repo root) — a single-page dashboard
with an eleven-tab strip. Drive it by starting the Streamlit server, then
running the headless-Chromium driver at
`.claude/skills/run-maddengm-dashboard/driver.py` against it. No `chromium-cli`
in this container — the driver is a small Playwright script instead.

The tab labels are short and emoji-prefixed, and the driver matches them
literally (see Gotchas):

```
🏠 Home   📊 Schemes   💪 Wear       🏈 Trades    🏛️ Dynasty   📋 Roster
🏆 Awards 🎯 Coach DNA 📈 Progression 🗂️ Raw Data 🤖 AI GM
```

Each tab's own header still carries its long name ("Trade Machine",
"Roster Explorer", ...), which is why those strings appear on the page but
are not clickable as tabs.

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

Needs **Python 3.10+** and **Streamlit 1.51+**. 3.9 was dropped: it caps
Streamlit at 1.50, which has no `width` parameter on `st.plotly_chart`, and
`app.py` uses `width="stretch"` throughout. CI builds 3.10 and 3.11.

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
python3 .claude/skills/run-maddengm-dashboard/driver.py "🏈 Trades" "📋 Roster"
```

Screenshots land in `.claude/skills/run-maddengm-dashboard/shots/`
(`00_home.png`, `01_🏈_Trades.png`, `02_📋_Roster.png`, ...). The
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

227 tests pass across 12 files in `tests/`.

`tests/test_app_smoke.py` is the one that actually runs `app.py`, via
Streamlit's `AppTest` — in-process, no browser, ~2s. CI otherwise only
`py_compile`s `app.py`, so that file is what catches a module raising at
import or a Streamlit kwarg being removed. The driver below is still worth
running for anything visual; `AppTest` cannot see layout.

## Gotchas

- **`playwright install` / browser auto-download does nothing here** — the
  environment sets `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` and pre-installs
  Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`. Pass that
  path explicitly as `executable_path` (the driver already does) — the
  default `p.chromium.launch()` looks for a different revision path and
  fails with "executable doesn't exist".
- **Pass the emoji tab label, not the long name.** The driver does
  `page.click(f"text={tab}")`, a literal match. `"Trade Machine"` and
  `"Roster Explorer"` were the labels before the strip was shortened to fit
  1366px; passing them now hangs for the full 30s and dies with
  `TimeoutError: waiting for locator("text=Trade Machine")`. Use `"🏈 Trades"`
  and `"📋 Roster"`. Those long names do still appear on the page — as each
  tab's own header — which is why the failure looks puzzling rather than
  obviously "no such tab".
- **`curl` on `/` only proves the Streamlit shell loaded**, not that the app
  rendered — the page body is a near-empty HTML shell until the client JS
  connects over websocket and Streamlit runs `app.py` server-side. Always
  drive it with the Playwright script and `wait_for_selector` on real
  content (e.g. `"text=Franchise Key Performance Indicators"`), not just a
  200 from `curl`.
- **IPv6 bind warning is harmless** — `streamlit run` logs "Could not bind
  IPv6 wildcard address :::8501; falling back to 0.0.0.0:8501" on startup in
  this container; the server still comes up fine on `localhost:8501`.
