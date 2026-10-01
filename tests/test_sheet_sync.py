"""
Google Sheet sync must never touch the local game log.

The sync used to write the sheet's CSV over data/game_logs.csv as its
offline copy, so a game logged through the entry form (which appends to
that file) and not yet in the sheet was deleted on the next sync. The
copy now lives in its own file, and the form is withdrawn while the
dashboard is showing the sheet, since a logged game wouldn't appear.

The app is run for real (AppTest) with urlopen replaced, so this covers
the sidebar wiring, not just a helper.
"""

import io
import os
import pathlib
import shutil
import urllib.request

import pytest

pytest.importorskip("streamlit.testing.v1", reason="AppTest needs streamlit >= 1.28")

from streamlit.testing.v1 import AppTest  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_APP = str(_ROOT / "app.py")
_LOG = _ROOT / "data" / "game_logs.csv"
_CACHE = _ROOT / "data" / "game_logs_sheet_cache.csv"
# One URL per test: the app caches each URL's fetch for 120s, so a
# shared URL would hand a later test an earlier test's result.
_URL = "https://example.com/{}.csv"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Back up the log and remove any sheet cache; restore both after."""
    backup = tmp_path / "game_logs.csv"
    shutil.copy(_LOG, backup)
    cache_backup = tmp_path / "cache.csv"
    had_cache = _CACHE.exists()
    if had_cache:
        shutil.move(_CACHE, cache_backup)
    try:
        yield monkeypatch
    finally:
        shutil.copy(backup, _LOG)
        if _CACHE.exists():
            _CACHE.unlink()
        if had_cache:
            shutil.move(cache_backup, _CACHE)


def _run_with_sheet(name):
    at = AppTest.from_file(_APP, default_timeout=120).run()
    url = _URL.format(name)
    [t for t in at.text_input if t.label == "Google Sheet CSV URL"][0].set_value(url).run()
    return at


def _sheet_without_last_game() -> bytes:
    lines = _LOG.read_bytes().rstrip(b"\n").split(b"\n")
    return b"\n".join(lines[:-1]) + b"\n"


def test_sheet_sync_leaves_the_local_log_alone(isolated_data):
    local = _LOG.read_bytes()
    sheet = _sheet_without_last_game()
    isolated_data.setattr(urllib.request, "urlopen", lambda url, timeout=20: _Resp(sheet))

    at = _run_with_sheet("sync")

    assert not at.exception, at.exception
    assert _LOG.read_bytes() == local, "sync overwrote the local game log"
    assert _CACHE.read_bytes() == sheet
    assert any("Live Sheet Synced" in str(s.value) for s in at.sidebar.success)


def test_entry_form_is_withdrawn_while_showing_the_sheet(isolated_data):
    isolated_data.setattr(urllib.request, "urlopen",
                          lambda url, timeout=20: _Resp(_sheet_without_last_game()))
    at = _run_with_sheet("form")
    assert any("add this game there" in str(i.value) for i in at.info)
    assert "Time of possession" not in [t.label for t in at.text_input]


def test_unreachable_sheet_falls_back_to_last_synced_copy(isolated_data):
    sheet = _sheet_without_last_game()
    _CACHE.write_bytes(sheet)
    os.utime(_CACHE)

    def fail(url, timeout=20):
        raise OSError("offline")
    isolated_data.setattr(urllib.request, "urlopen", fail)

    at = _run_with_sheet("offline")

    assert not at.exception, at.exception
    assert any("last synced copy" in str(i.value) for i in at.sidebar.info)
    assert any("Sheet sync failed" in str(w.value) for w in at.sidebar.warning)
