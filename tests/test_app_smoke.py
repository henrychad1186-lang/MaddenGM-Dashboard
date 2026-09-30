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
import pathlib

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
    """
    assert len(app.tabs) == EXPECTED_TABS


def test_the_page_rendered_content(app):
    """A script that no-ops early would still pass the assertions above."""
    assert len(app.metric) > 0, "no metrics rendered"
    assert any(str(m.value).strip() for m in app.metric), "all metrics empty"


def test_no_streamlit_deprecations(app):
    """A deprecated kwarg works until the release that removes it.

    `use_container_width` was deprecated for months before removal; the
    only signal was a log line nobody reads. Failing here turns that
    notice into a CI failure while the old call still works, instead of
    a crash on the release that drops it. The scheduled newest-deps
    workflow runs this against each new Streamlit as it ships.
    """
    assert not app.deprecations, "\n\n".join(app.deprecations)
