#!/bin/bash
set -euo pipefail

# Only run in Claude Code on the web — local/CLI sessions manage their own
# Python environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Async: the session starts immediately instead of waiting on these pip
# installs. Trade-off is a brief window where a tool call in the very
# first turn could run before dependencies finish — acceptable here since
# this repo's deps are lightweight and usually already cached.
echo '{"async": true, "asyncTimeout": 300000}'

cd "$CLAUDE_PROJECT_DIR"

# Note: deliberately NOT running `pip install --upgrade pip` here — in
# this environment's base image, pip is a Debian-managed package without
# proper RECORD metadata, so upgrading it fails with "Cannot uninstall
# pip 24.0, RECORD file not found" (exit 1), which would abort this
# entire script under `set -e` before anything else installs. The
# preinstalled pip is new enough for everything below.

# App dependencies (requirements.txt — this repo is pip-only, no
# pyproject.toml/Poetry).
python3 -m pip install -r requirements.txt

# Test + lint tooling — matches .github/workflows/python-package.yml
# (pytest tests/, flake8 .) so `pytest` and `flake8` work immediately.
python3 -m pip install pytest flake8

# Playwright — used by the bundled run-maddengm-dashboard skill to drive
# the app headlessly for screenshots/verification. Browsers are expected
# to already be provided by the environment (PLAYWRIGHT_BROWSERS_PATH);
# this only installs the Python package itself.
python3 -m pip install playwright

# Start the dashboard so it's already serving when the session opens. One
# server only, on the port the run-maddengm-dashboard skill expects; skipped
# if something is already listening there. setsid detaches it from this
# async hook so it outlives the script.
if ! curl -sf http://localhost:8501 >/dev/null 2>&1; then
  setsid nohup python3 -m streamlit run app.py \
    --server.headless true --server.port 8501 \
    > /tmp/streamlit.log 2>&1 < /dev/null &
fi
