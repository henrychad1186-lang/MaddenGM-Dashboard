"""The Home tab's backfill form, run through the real app (AppTest)."""

import pytest

pytest.importorskip("streamlit.testing.v1", reason="AppTest needs streamlit >= 1.28")

from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.test_app_smoke import _APP, _TIMEOUT  # noqa: E402

_INPUTS = ("backfill_td_att", "backfill_td_conv", "backfill_rz_att")


def _values(at, gid):
    return [at.number_input(key=f"{k}_{gid}").value for k in _INPUTS]


def test_switching_games_prefills_the_new_game():
    # One key per input kept the previous game's numbers on screen after
    # a switch (43's 12/3 shown for 37, which holds 12/1), and Save wrote
    # them onto the newly picked game.
    at = AppTest.from_file(_APP, default_timeout=_TIMEOUT)
    at.session_state["backfill_game"] = 43
    at.run()
    assert _values(at, 43)[:2] == [12, 3]
    at.selectbox(key="backfill_game").set_value(37).run()
    assert not at.exception
    assert _values(at, 37)[:2] == [12, 1]


def test_games_with_estimated_attempts_can_be_corrected():
    # Only "missing" games were offered; the imported games carry an
    # estimated 12 attempts, so most of them could never be reached.
    at = AppTest.from_file(_APP, default_timeout=_TIMEOUT)
    at.run()
    options = at.selectbox(key="backfill_game").options
    assert any(o.startswith("#38 ") for o in options)
    assert options[0].endswith("— missing")
