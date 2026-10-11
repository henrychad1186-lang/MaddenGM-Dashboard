"""
Does app.py actually run?

Nothing else in this suite answers that. CI only does `py_compile app.py`,
which catches syntax errors and nothing else, and no other test imports
the module — so every Streamlit call in it was unverified, and a module
that raises on import looks identical to a healthy app from CI's point
of view.

`AppTest` executes the whole script in-process, no browser. Streamlit
reruns the entire script on every interaction, so one `run()` covers all
tab bodies, not just the visible one.

This is also the tripwire for dependency drift. `requirements.txt` has no
upper bounds, so each Python version resolves a different stack — pandas
2.x against 3.x, anthropic 0.x against 1.x — and a Streamlit release that
removes or renames a kwarg the app passes (as `use_container_width` was,
in favour of `width=`) breaks at runtime, not at compile time. When that
happens, this is what says so.

## What this deliberately does NOT assert

An earlier draft also checked `at.error` for the loader's "roster CSV is
missing required column(s)" banner. It was verified against a real broken
CSV and **passed anyway**: the loader correctly recorded the problem and
fell back to a single demo row, but the `st.error` — raised inside a
`st.tabs` container — surfaces nowhere in AppTest's element tree, not even
when descending into `at.tabs[i].error`. A false negative is worse than no
assertion, so that behaviour is left to `tests/test_roster_loading.py`,
which checks `SOURCE_COLUMN_ISSUES` directly.

Asserting on `src.roster` module globals from here would be unreliable
too: `test_roster_loading.py` reloads that module against a temp CSV, so
what its globals hold depends on test ordering.
"""

import logging
import os
import pathlib
import warnings

import pytest

pytest.importorskip("streamlit.testing.v1",
                    reason="AppTest needs streamlit >= 1.28")

from streamlit.testing.v1 import AppTest  # noqa: E402

# AppTest resolves a relative path against the file that calls it, not the
# working directory, so "app.py" would look for tests/app.py.
_APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")

# The app reads its CSVs and builds every tab on load; a warm run takes
# ~2s, so this is slack for a cold CI runner, not an expected duration.
_TIMEOUT = 120

EXPECTED_TABS = 13
# `app.tabs` is flat: it returns nested tabs alongside the top-level
# strip, so the count is not the number of tabs in the header. Scheme
# Performance holds three (Performance / Offense / Defense).
EXPECTED_NESTED_TABS = 3
TOP_LEVEL_TAB_LABELS = (
    "🏠 Home", "📊 Schemes", "💪 Wear", "🏈 Trades", "🏛️ Dynasty",
    "📋 Roster", "🏆 Awards", "🎯 Coach DNA", "📈 Progression",
    "🗂️ Raw Data", "🤖 AI GM", "💬 Chat", "🔎 Draft",
)
# The sub-tabs inside Scheme Performance, which share the flat list.
NESTED_TAB_LABELS = ("📈 Performance", "🏈 Offense", "🛡️ Defense")


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


@pytest.fixture(scope="module")
def app():
    """Run app.py once and share the result across the assertions below.

    Also records Streamlit's deprecation notices. Streamlit logs them
    (never raises, and only renders them when error details are on), to
    a logger that doesn't propagate, so pytest's caplog can't see them.
    """
    dep_logger = logging.getLogger("streamlit.deprecation_util")
    collect = _Collect()
    dep_logger.addHandler(collect)
    try:
        at = AppTest.from_file(_APP, default_timeout=_TIMEOUT)
        at.run()
    finally:
        dep_logger.removeHandler(collect)
    at.deprecations = collect.messages
    return at


def test_the_app_starts_without_raising(app):
    """The failure this exists for.

    `adff73d` changed the roster CSV headings and `src/roster.py` began
    raising `KeyError: 'Pos'` at import, so `streamlit run app.py` died
    before rendering anything. Verified to fail when app.py raises.
    """
    assert not app.exception, "\n".join(str(e) for e in app.exception)


def test_every_tab_is_built(app):
    """Streamlit executes all tab bodies on every run, not just the open one.

    So this covers every tab's worth of Streamlit calls — which is where
    a removed or renamed kwarg would surface.

    Counted as top-level plus nested rather than one total, because a
    flat total hides which of the two changed: adding a sub-tab and
    dropping a tab from the strip would leave it unmoved.
    """
    assert len(app.tabs) == EXPECTED_TABS + EXPECTED_NESTED_TABS


def test_the_top_level_strip_is_unchanged(app):
    """Nested tabs must not quietly alter the main strip.

    `app.tabs` is flat, so the labels are what distinguish the header
    from anything nested inside a tab body.
    """
    labels = [str(t.label) for t in app.tabs]
    missing = [t for t in TOP_LEVEL_TAB_LABELS if t not in labels]
    assert not missing, f"top-level tabs missing: {missing}"
    nested_missing = [t for t in NESTED_TAB_LABELS if t not in labels]
    assert not nested_missing, f"nested tabs missing: {nested_missing}"
    # Nothing unaccounted for: a tab added without updating either
    # tuple would otherwise slip through both checks above.
    assert set(labels) == set(TOP_LEVEL_TAB_LABELS) | set(NESTED_TAB_LABELS)


def test_the_page_rendered_content(app):
    """A script that no-ops early would still pass the assertions above."""
    assert len(app.metric) > 0, "no metrics rendered"
    assert any(str(m.value).strip() for m in app.metric), "all metrics empty"


def test_no_streamlit_deprecations(app):
    """A deprecated kwarg works until the release that removes it.

    `use_container_width` was deprecated for months before removal; the
    only signal was a log line nobody reads. This surfaces that notice
    while the old call still works, instead of a crash on the release
    that drops it.

    Warn-only by default: regular CI installs the latest Streamlit, so a
    new deprecation would otherwise turn every unrelated PR red. The
    dependency canary's newest job sets STRICT_DEPRECATIONS=1, which
    fails the run and opens the canary issue.
    """
    if not app.deprecations:
        return
    notices = "\n\n".join(app.deprecations)
    if os.environ.get("STRICT_DEPRECATIONS") == "1":
        pytest.fail(f"Streamlit deprecation notice(s):\n\n{notices}")
    warnings.warn(f"Streamlit deprecation notice(s):\n\n{notices}", UserWarning)
    # Not captured by pytest, so it shows on the Actions run page.
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### ⚠️ Streamlit deprecation notices\n\n"
                     + "".join(f"- {m.splitlines()[0]}\n" for m in app.deprecations)
                     + "\nWarning only here; the dependency canary fails on these.\n")


def test_empty_position_rooms_get_a_grade_card(app):
    """get_position_grades skips empty rooms, so the Roster grid dropped
    exactly the positions Home lists as top needs (FB, LG, MLB on the
    shipped roster). They now render as empty cards."""
    html = " ".join(str(m.value) for m in app.markdown)
    for pos in ("FB", "LG", "MLB"):
        assert f">{pos}</div>" in html and "No starter" in html, pos


def test_cap_what_if_is_not_called_a_cap_position(app):
    """Savings minus dead cap if everyone were released was shown as
    "Net Cap Position" with a Healthy/Tight badge and printed "$-400.1M"."""
    labels = {m.label: m.value for m in app.metric}
    assert "Net Cap Position" not in labels
    value = labels["Net if All Released"]
    assert value.startswith(("−$", "+$")), value


def test_peak_win_pct_skips_the_opening_games(app):
    """Over every game the peak was 100% for any team that won its opener."""
    labels = {m.label: m.value for m in app.metric}
    assert "Peak Win %" not in labels
    peak = next(v for k, v in labels.items() if k.startswith("Peak Win % (game"))
    assert peak != "100.0%"
