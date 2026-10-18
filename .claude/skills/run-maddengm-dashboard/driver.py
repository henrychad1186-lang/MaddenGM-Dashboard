#!/usr/bin/env python3
"""Drive the MaddenGM Streamlit dashboard with headless Chromium.

Usage:
    python3 driver.py [tab-text ...]

With no args: loads the home page (the Home tab, the default) and
screenshots it. Each extra arg is clicked as a tab label, emoji included
(e.g. "🏈 Trades"), in order, with a screenshot after each click.
Prints any browser console errors at the end and exits 1 if there
were any.

Requires the app already running at http://localhost:8501 (see
SKILL.md "Run" section) and playwright installed
(`pip install playwright`, browsers already present at
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers in this container).

## Why `_settle` exists

Waiting on the main column alone produced screenshots that looked
plausible and were wrong. At the moment the old driver fired, with
"Franchise Key Performance Indicators" already on screen:

    stStatusWidget   visible      -> the script was still running
    stSelectbox      not visible  -> sidebar widgets had not painted
    stTextInput      not visible
    document.fonts   "loading"

The sidebar came out as empty grey boxes — no "Google Sheet CSV URL",
no team picker — which reads as a UI regression rather than a capture
artifact, and cost a round of investigating a bug that did not exist.
A screenshot tool that quietly captures a half-painted page is worse
than one that fails, so `_settle` blocks on all four signals and
raises if any of them never arrives.
"""
import os
import sys
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

APP_URL = "http://localhost:8501"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "shots")
SETTLE_MS = 20000

# A widget that only exists in the sidebar, so the probe cannot be
# satisfied by the main column having painted first. It must also be
# one that is *expected* to be visible: `stSelectbox` looks like the
# obvious choice and never settles, because the first one in DOM order
# sits inside the collapsed "Dashboard Filters" expander and so is
# hidden by design. The Google Sheet input is in the expander that
# opens by default, and was one of the controls missing from the
# half-painted captures this guard exists to prevent.
SIDEBAR_WIDGET = '[data-testid="stSidebar"] [data-testid="stTextInputField"]'


def _settle(page, what: str) -> None:
    """Block until Streamlit has finished painting, or raise saying why.

    Four signals, because no one of them is sufficient: content proves
    the script produced output, the status widget clearing proves the
    run finished, the sidebar widget proves the slowest region mounted,
    and fonts.ready proves text will measure and paint at its final
    size rather than reflowing after the capture.
    """
    checks = (
        ("main content", lambda: page.wait_for_selector(
            "text=Franchise Key Performance Indicators",
            state="visible", timeout=SETTLE_MS)),
        ("script run to finish", lambda: page.wait_for_selector(
            '[data-testid="stStatusWidget"]', state="hidden",
            timeout=SETTLE_MS)),
        ("sidebar widgets", lambda: page.wait_for_selector(
            SIDEBAR_WIDGET, state="visible", timeout=SETTLE_MS)),
        ("web fonts", lambda: page.wait_for_function(
            "document.fonts.status === 'loaded'", timeout=SETTLE_MS)),
    )
    for label, wait in checks:
        try:
            wait()
        except PlaywrightError as exc:
            raise RuntimeError(
                f"{what}: waited {SETTLE_MS}ms for {label} and it never "
                f"settled — refusing to screenshot a half-rendered page. "
                f"({type(exc).__name__})") from exc


def main(tabs):
    os.makedirs(SHOT_DIR, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        page.goto(APP_URL, wait_until="networkidle", timeout=30000)
        _settle(page, "home")
        shot = os.path.join(SHOT_DIR, "00_home.png")
        page.screenshot(path=shot, full_page=True)
        print(f"screenshot: {shot}")

        for i, tab in enumerate(tabs, start=1):
            page.click(f"text={tab}")
            # Not a fixed sleep: a tab click triggers a rerun, and how
            # long it takes depends on the tab. Waiting a flat 1.5s was
            # either wasteful or too short, with no way to tell which.
            _settle(page, f"tab {tab!r}")
            shot = os.path.join(SHOT_DIR, f"{i:02d}_{tab.replace(' ', '_')}.png")
            page.screenshot(path=shot, full_page=True)
            print(f"screenshot: {shot}")

        browser.close()

    print("console errors:", errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
