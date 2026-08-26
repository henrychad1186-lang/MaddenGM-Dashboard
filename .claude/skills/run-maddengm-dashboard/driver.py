#!/usr/bin/env python3
"""Drive the MaddenGM Streamlit dashboard with headless Chromium.

Usage:
    python3 driver.py [tab-text ...]

With no args: loads the home page (Scheme Performance tab, the
default) and screenshots it. Each extra arg is clicked as a tab label
(e.g. "Trade Machine") in order, with a screenshot after each click.
Prints any browser console errors at the end and exits 1 if there
were any.

Requires the app already running at http://localhost:8501 (see
SKILL.md "Run" section) and playwright installed
(`pip install playwright`, browsers already present at
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers in this container).
"""
import os
import sys
from playwright.sync_api import sync_playwright

APP_URL = "http://localhost:8501"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "shots")


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
        page.wait_for_selector(
            "text=Franchise Key Performance Indicators", timeout=15000
        )
        shot = os.path.join(SHOT_DIR, "00_home.png")
        page.screenshot(path=shot, full_page=True)
        print(f"screenshot: {shot}")

        for i, tab in enumerate(tabs, start=1):
            page.click(f"text={tab}")
            page.wait_for_timeout(1500)
            shot = os.path.join(SHOT_DIR, f"{i:02d}_{tab.replace(' ', '_')}.png")
            page.screenshot(path=shot, full_page=True)
            print(f"screenshot: {shot}")

        browser.close()

    print("console errors:", errors)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
