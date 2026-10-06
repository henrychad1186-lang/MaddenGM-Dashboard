"""Per-user chat storage: user keys, the Sheets row format, backends."""

import json
import os

import pytest

from src import chat_store as cs


class WorksheetNotFound(Exception):
    """Same class name gspread raises; the backend matches on the name."""


class FakeWorksheet:
    """Models the grid: like the Sheets API, a write past row_count fails
    rather than growing the tab, and resize() truncates."""

    def __init__(self, rows=200):
        self.values, self.row_count, self.fail_update = [], rows, False

    def get_all_values(self):
        return [[str(c) for c in r] for r in self.values]  # Sheets returns text

    def clear(self):
        self.values = []

    def resize(self, rows=None, cols=None):
        if rows is not None:
            self.row_count = rows
            self.values = self.values[:rows]

    def update(self, values, range_name=None):
        assert range_name == "A1"
        if self.fail_update:
            raise RuntimeError("network")
        if len(values) > self.row_count:
            raise RuntimeError("exceeds grid limits")
        rows = [list(r) for r in values]
        self.values = rows + self.values[len(rows):]


class FakeSpreadsheet:
    def __init__(self):
        self.tabs, self.fail = {}, None

    def worksheet(self, title):
        if self.fail:
            raise self.fail
        if title not in self.tabs:
            raise WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, title, rows, cols):
        self.tabs[title] = FakeWorksheet(rows)
        return self.tabs[title]


def _store(team="GB", *pairs):
    store = {}
    conv = cs.new_conversation(store, team)
    for role, text in pairs:
        cs.append_message(conv, role, text)
    return store, conv


def test_user_key_is_stable_case_insensitive_and_hides_email():
    k = cs.user_key("Chad@Example.com ")
    assert k == cs.user_key("chad@example.com") and len(k) == 16
    assert "chad" not in k and k != cs.user_key("other@example.com")


def test_rows_round_trip_through_sheet_text():
    store, conv = _store("GB", ("user", "Trade Jacobs?"), ("assistant", 'No — "ride it out".'))
    other, _ = _store("CHI", ("user", "hi"))
    store.update(other)
    rows = [[str(c) for c in r] for r in [cs.SHEET_HEADER] + cs.store_to_rows(store)]
    back = cs.rows_to_store(rows)
    (got,) = back["GB"]
    assert got["id"] == conv["id"] and got["title"] == "Trade Jacobs?"
    assert [m["content"] for m in got["messages"]] == ["Trade Jacobs?", 'No — "ride it out".']
    assert got["updated"] == pytest.approx(conv["updated"]) and "CHI" in back


def test_rows_to_store_tolerates_hand_edits():
    rows = [cs.SHEET_HEADER,
            ["GB", "c1", "t", "1", "2", "1", "assistant", "second"],
            ["GB", "c1", "t", "1", "2", "0", "user", "first"],   # out of order
            ["GB", "c1", "t", "1", "2", "2", "system", "dropped"],  # bad role
            ["", "", "", "", "", "", "", ""],                     # blank row
            ["GB", "c2"]]                                         # short row, no messages
    (conv,) = cs.rows_to_store(rows)["GB"]
    assert [m["content"] for m in conv["messages"]] == ["first", "second"]


def test_long_messages_fit_a_sheet_cell():
    store, _ = _store("GB", ("user", "x" * 60_000))
    (row,) = cs.store_to_rows(store)
    assert len(row[-1]) < 50_000 and row[-1].endswith("…[truncated]")


def test_sheets_backend_isolates_users():
    ss = FakeSpreadsheet()
    a = cs.SheetsBackend(ss, cs.user_key("a@x.com"), "sheet")
    b = cs.SheetsBackend(ss, cs.user_key("b@x.com"), "sheet")
    assert a.load() == {} and b.load() == {}          # no tab yet: empty, not error
    sa, _ = _store("GB", ("user", "mine"))
    sb, _ = _store("GB", ("user", "theirs"))
    assert a.save(sa) and b.save(sb)
    assert len(ss.tabs) == 2 and all("@" not in t for t in ss.tabs)
    assert a.load()["GB"][0]["messages"][0]["content"] == "mine"
    assert b.load()["GB"][0]["messages"][0]["content"] == "theirs"


def test_sheets_error_is_none_not_empty():
    # A network error must not read as "no chats", or the next save would
    # wipe the user's tab.
    ss = FakeSpreadsheet()
    ss.fail = ConnectionError("down")
    backend = cs.SheetsBackend(ss, "k", "sheet")
    assert backend.load() is None and backend.save({}) is False


def test_resolve_signed_in_with_sheet():
    ss = FakeSpreadsheet()
    backend, note = cs.resolve_backend("a@x.com", lambda: ss)
    assert isinstance(backend, cs.SheetsBackend) and note == ""


def test_resolve_sheet_open_failure_saves_nothing():
    def boom():
        raise PermissionError("not shared with the service account")
    backend, note = cs.resolve_backend("a@x.com", boom)
    assert backend is None and "PermissionError" in note


def test_resolve_signed_in_without_sheet_uses_per_user_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "USER_DIR", str(tmp_path))
    backend, _ = cs.resolve_backend("a@x.com")
    assert isinstance(backend, cs.FileBackend)
    assert backend.path == os.path.join(str(tmp_path), cs.user_key("a@x.com") + ".json")
    store, _ = _store("GB", ("user", "hi"))
    assert backend.save(store) and backend.load() == json.loads(json.dumps(store))


def test_resolve_anonymous():
    assert cs.resolve_backend(None) == (None, "")          # shared deployment: nothing saved
    backend, _ = cs.resolve_backend(None, shared_file_ok=True)
    assert backend.path == cs.DEFAULT_PATH                 # owner's local opt-in


def test_unreadable_file_is_none(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{}")
    p.chmod(0)
    backend = cs.FileBackend(str(p), "file")
    if os.access(str(p), os.R_OK):                         # running as root
        pytest.skip("root can read mode-0 files")
    assert backend.load() is None


def _big_store(n_msgs, team="GB"):
    store = {}
    for c in range(n_msgs // 10):
        conv = cs.new_conversation(store, team)
        for i in range(10):
            cs.append_message(conv, "user" if i % 2 == 0 else "assistant", f"m{c}-{i}")
    return store


def test_sheets_save_grows_past_the_initial_200_rows():
    ss = FakeSpreadsheet()
    backend = cs.SheetsBackend(ss, "k", "tab")
    store = _big_store(300)
    assert backend.save(store) is True
    assert len(ss.tabs["chats_k"].values) == 301  # header + one row per message
    assert sum(len(c["messages"]) for c in backend.load()["GB"]) == 300


def test_sheets_save_trims_rows_left_by_a_bigger_store():
    ss = FakeSpreadsheet()
    backend = cs.SheetsBackend(ss, "k", "tab")
    backend.save(_big_store(300))
    backend.save(_big_store(20))
    assert ss.tabs["chats_k"].row_count == 21
    assert sum(len(c["messages"]) for c in backend.load()["GB"]) == 20


def test_failed_sheets_write_keeps_the_previous_history():
    ss = FakeSpreadsheet()
    backend = cs.SheetsBackend(ss, "k", "tab")
    backend.save(_big_store(20))
    ss.tabs["chats_k"].fail_update = True
    assert backend.save(_big_store(30)) is False
    assert sum(len(c["messages"]) for c in backend.load()["GB"]) == 20
