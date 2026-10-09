"""Game logs the sidebar must load without hiding games or crashing.

Run through the real app (AppTest) with the sheet fetch replaced, the
same way tests/test_sheet_sync.py does.
"""

import pytest

pytest.importorskip("streamlit.testing.v1", reason="AppTest needs streamlit >= 1.28")

from src import sheet_fetch  # noqa: E402
from tests.test_sheet_sync import _Resp, _run_with_sheet, isolated_data  # noqa: E402,F401


def _serve(monkeypatch, csv: str):
    monkeypatch.setattr(sheet_fetch, "_open", lambda url, extra_hosts=(): _Resp(csv.encode()))


def _shown(at) -> str:
    return " ".join(str(c.value) for c in at.sidebar.caption)


def test_result_only_log_is_not_filtered_to_nothing(isolated_data):  # noqa: F811 - pytest fixture
    # No score columns: Result stayed "W"/"L", matched none of the
    # WIN/LOSS/TIE filter options, and every game was hidden.
    _serve(isolated_data, "Opponent,Result,Pass_Yards,Rush_Yards\n"
                          "CHI,W,200,90\nDET,L,150,60\nMIN,,180,70\n")
    at = _run_with_sheet("result-only")
    assert not at.exception, at.exception
    assert "Showing 3 of 3 games" in _shown(at)


def test_non_clock_time_of_possession_does_not_crash(isolated_data):  # noqa: F811 - pytest fixture
    # "N/A" used to pass through as text, making TOP_Mins a string
    # column; the sidebar's .sub() then raised for the whole app.
    _serve(isolated_data, "Opponent,Points_For,Points_Against,TOP\n"
                          "CHI,24,17,N/A\nDET,10,20,22:30\nMIN,31,3,28\n")
    at = _run_with_sheet("bad-top")
    assert not at.exception, at.exception
    assert "Showing 3 of 3 games" in _shown(at)
