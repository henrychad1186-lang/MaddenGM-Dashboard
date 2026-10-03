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

import glob
import hashlib
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
_CACHE_GLOB = str(_ROOT / "data" / "game_logs_sheet_cache_*.csv")
# One URL per test: the app caches each URL's fetch for 120s, so a
# shared URL would hand a later test an earlier test's result.
_URL = "https://example.com/{}.csv"


def _cache_for(name) -> pathlib.Path:
    """Mirror of app._sheet_cache_path: one cache file per sheet URL."""
    key = hashlib.sha256(_URL.format(name).encode("utf-8")).hexdigest()[:16]
    return _ROOT / "data" / f"game_logs_sheet_cache_{key}.csv"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Back up the log and set any sheet caches aside; restore all after."""
    backup = tmp_path / "game_logs.csv"
    shutil.copy(_LOG, backup)
    stash = tmp_path / "caches"
    stash.mkdir()
    existing = [pathlib.Path(p) for p in glob.glob(_CACHE_GLOB)]
    for p in existing:
        shutil.move(p, stash / p.name)
    try:
        yield monkeypatch
    finally:
        shutil.copy(backup, _LOG)
        for p in glob.glob(_CACHE_GLOB):
            os.unlink(p)
        for p in stash.iterdir():
            shutil.move(p, _ROOT / "data" / p.name)


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
    assert _cache_for("sync").read_bytes() == sheet
    assert any("Live Sheet Synced" in str(s.value) for s in at.sidebar.success)


def test_entry_form_is_withdrawn_while_showing_the_sheet(isolated_data):
    isolated_data.setattr(urllib.request, "urlopen",
                          lambda url, timeout=20: _Resp(_sheet_without_last_game()))
    at = _run_with_sheet("form")
    assert any("add this game there" in str(i.value) for i in at.info)
    assert "Time of possession" not in [t.label for t in at.text_input]


def test_unreachable_sheet_falls_back_to_last_synced_copy(isolated_data):
    sheet = _sheet_without_last_game()
    _cache_for("offline").write_bytes(sheet)

    def fail(url, timeout=20):
        raise OSError("offline")
    isolated_data.setattr(urllib.request, "urlopen", fail)

    at = _run_with_sheet("offline")

    assert not at.exception, at.exception
    assert any("last synced copy" in str(i.value) for i in at.sidebar.info)
    assert any("Sheet sync failed" in str(w.value) for w in at.sidebar.warning)


def test_unreachable_sheet_never_shows_another_sheets_copy(isolated_data):
    # Sheet A syncs (and is cached); then the URL is switched to sheet B,
    # which can't be reached. B must not be shown A's games.
    sheet_a = _sheet_without_last_game()

    def serve(url, timeout=20):
        if url == _URL.format("sheet-a"):
            return _Resp(sheet_a)
        raise OSError("offline")
    isolated_data.setattr(urllib.request, "urlopen", serve)

    at = _run_with_sheet("sheet-a")
    assert any("Live Sheet Synced" in str(s.value) for s in at.sidebar.success)

    url_box = [t for t in at.text_input if t.label == "Google Sheet CSV URL"][0]
    url_box.set_value(_URL.format("sheet-b")).run()

    assert not at.exception, at.exception
    assert not any("last synced copy" in str(i.value) for i in at.sidebar.info)
    assert any("Falling back to local data" in str(i.value) for i in at.sidebar.info)
