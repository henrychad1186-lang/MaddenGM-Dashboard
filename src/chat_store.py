"""
Conversation store for the GM Chat tab.

Conversations are kept per team, the way a chat sidebar keeps a list of
past threads: each one has an id, a title (taken from its first
question), a timestamp and its messages. The store is a plain dict so it
can sit in `st.session_state` and be written to disk as JSON unchanged.

Persistence is best-effort. On Streamlit Community Cloud the container
filesystem is wiped on restart, so saved chats survive a browser refresh
there but not a redeploy; locally they survive everything. A missing,
unreadable or corrupt file just starts an empty store instead of raising,
because losing chat history must never take the dashboard down with it.
"""

import hashlib
import json
import os
import time
import uuid

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "chat_history.json")
USER_DIR = os.path.join(os.path.dirname(DEFAULT_PATH), "chat_history")

_TITLE_MAX = 40
# A long-running store would otherwise grow without bound; the oldest
# threads past this count are dropped on save.
MAX_CONVERSATIONS_PER_TEAM = 50


def load(path: str = DEFAULT_PATH) -> dict:
    """Read the store from disk, or return an empty one on any problem."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    store = {}
    for team, convs in data.items():
        if not isinstance(convs, list):
            continue
        clean = [c for c in (_clean_conversation(c) for c in convs) if c]
        if clean:
            store[str(team)] = clean
    return store


def _clean_conversation(conv) -> "dict | None":
    """A well-formed copy of one saved conversation, or None to drop it.

    The file is hand-editable and outlives app versions, so valid JSON is
    not enough: a bare `1` in a team's list used to reach `conv.get()`
    and take the tab down. Bad messages are dropped individually rather
    than discarding the whole thread.
    """
    if not isinstance(conv, dict) or not isinstance(conv.get("id"), str):
        return None
    msgs = conv.get("messages")
    if not isinstance(msgs, list):
        return None
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in msgs
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    ]

    def _num(key):
        v = conv.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0

    title = conv.get("title")
    return {
        "id": conv["id"],
        "title": title if isinstance(title, str) and title else "New chat",
        "created": _num("created"),
        "updated": _num("updated"),
        "messages": messages,
    }


def _trim(store: dict) -> dict:
    return {
        team: sorted(convs, key=lambda c: c.get("updated", 0),
                     reverse=True)[:MAX_CONVERSATIONS_PER_TEAM]
        for team, convs in store.items()
    }


def save(store: dict, path: str = DEFAULT_PATH) -> bool:
    """Write the store to disk atomically. Returns False if it couldn't."""
    trimmed = _trim(store)
    tmp = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(trimmed, fh, indent=1)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def list_conversations(store: dict, team: str) -> "list[dict]":
    """Team's conversations, most recently active first."""
    return sorted(store.get(team, []), key=lambda c: c.get("updated", 0), reverse=True)


def get(store: dict, team: str, conv_id: "str | None") -> "dict | None":
    for conv in store.get(team, []):
        if conv.get("id") == conv_id:
            return conv
    return None


def new_conversation(store: dict, team: str) -> dict:
    """Create an empty conversation for `team` and return it."""
    conv = {
        "id": uuid.uuid4().hex[:12],
        "title": "New chat",
        "created": time.time(),
        "updated": time.time(),
        "messages": [],
    }
    store.setdefault(team, []).append(conv)
    return conv


def delete_conversation(store: dict, team: str, conv_id: str) -> None:
    store[team] = [c for c in store.get(team, []) if c.get("id") != conv_id]


def make_title(text: str) -> str:
    """Title a conversation from its first question, on a word boundary."""
    text = " ".join(text.split())
    if len(text) <= _TITLE_MAX:
        return text or "New chat"
    cut = text[:_TITLE_MAX].rsplit(" ", 1)[0] or text[:_TITLE_MAX]
    return cut.rstrip(",.;:") + "…"


def append_message(conv: dict, role: str, content: str) -> None:
    """Add a turn; the first user turn also names the conversation."""
    if role == "user" and not any(m["role"] == "user" for m in conv["messages"]):
        conv["title"] = make_title(content)
    conv["messages"].append({"role": role, "content": content})
    conv["updated"] = time.time()


def export_markdown(conv: dict, team: str) -> str:
    """Render a conversation as Markdown for download."""
    lines = [f"# {conv['title']}", "", f"_GM Chat — {team}_", ""]
    for m in conv["messages"]:
        who = "**You:**" if m["role"] == "user" else "**AI GM:**"
        lines += [who, "", m["content"], ""]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# PER-USER STORAGE
# ──────────────────────────────────────────────
# A backend has load() -> dict | None and save(store) -> bool. load()
# returns None when it could not tell what is stored (network error,
# permission error): the caller must then not save, or it would replace
# the user's real history with this session's. An empty dict means
# "nothing saved yet".

def user_key(identity: str) -> str:
    """Stable, non-reversible storage key for a signed-in user.

    Emails never appear in file or tab names; the same address in any
    case maps to the same key.
    """
    return hashlib.sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:16]


class FileBackend:
    """JSON file on the app's disk. Survives restarts locally; on
    Streamlit Community Cloud the disk is wiped on redeploy."""

    def __init__(self, path: str, label: str):
        self.path, self.label = path, label

    def load(self) -> "dict | None":
        if os.path.exists(self.path) and not os.access(self.path, os.R_OK):
            return None
        return load(self.path)

    def save(self, store: dict) -> bool:
        return save(store, self.path)


# Google Sheets caps a cell at 50,000 characters.
_CELL_MAX = 49_000
SHEET_HEADER = ["team", "conv_id", "title", "created", "updated", "idx", "role", "content"]


def store_to_rows(store: dict) -> "list[list]":
    """One row per message, newest conversations first."""
    rows = []
    for team, convs in _trim(store).items():
        for conv in convs:
            for i, m in enumerate(conv["messages"]):
                content = m["content"]
                if len(content) > _CELL_MAX:
                    content = content[:_CELL_MAX] + " …[truncated]"
                rows.append([team, conv["id"], conv["title"], conv.get("created", 0.0),
                             conv.get("updated", 0.0), i, m["role"], content])
    return rows


def rows_to_store(rows: "list[list]") -> dict:
    """Inverse of store_to_rows. Tolerates a missing header, short rows,
    stringified numbers (Sheets returns every cell as text) and rows
    edited by hand; anything unusable is dropped via _clean_conversation."""
    if rows and [str(c).strip().lower() for c in rows[0][:len(SHEET_HEADER)]] == SHEET_HEADER:
        rows = rows[1:]

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    convs = {}
    for r in rows:
        r = list(r) + [""] * (len(SHEET_HEADER) - len(r))
        team, cid, title, created, updated, idx, role, content = r[:len(SHEET_HEADER)]
        if not team or not cid:
            continue
        conv = convs.setdefault((str(team), str(cid)), {
            "id": str(cid), "title": str(title), "created": _f(created),
            "updated": _f(updated), "messages": []})
        conv["messages"].append((_f(idx), {"role": str(role), "content": str(content)}))
    store = {}
    for (team, _), conv in convs.items():
        conv["messages"] = [m for _, m in sorted(conv["messages"], key=lambda t: t[0])]
        clean = _clean_conversation(conv)
        if clean and clean["messages"]:
            store.setdefault(team, []).append(clean)
    return store


class SheetsBackend:
    """One worksheet per user in a Google Sheet the app owner controls.

    A tab per user (named by user_key, never the email) keeps users from
    overwriting each other: each save rewrites only that user's tab.
    `spreadsheet` is a gspread Spreadsheet (or anything with the same
    worksheet / add_worksheet methods).
    """

    def __init__(self, spreadsheet, key: str, label: str):
        self.ss, self.title, self.label = spreadsheet, f"chats_{key}", label

    def _worksheet(self, create: bool):
        try:
            return self.ss.worksheet(self.title)
        except Exception as exc:  # noqa: BLE001 - gspread is an optional import
            if type(exc).__name__ != "WorksheetNotFound":
                raise
        if not create:
            return None
        return self.ss.add_worksheet(title=self.title, rows=200, cols=len(SHEET_HEADER))

    def load(self) -> "dict | None":
        try:
            ws = self._worksheet(create=False)
            return {} if ws is None else rows_to_store(ws.get_all_values())
        except Exception:  # noqa: BLE001 - unknown state: caller must not save
            return None

    def save(self, store: dict) -> bool:
        try:
            ws = self._worksheet(create=True)
            ws.clear()
            ws.update(values=[SHEET_HEADER] + store_to_rows(store), range_name="A1")
            return True
        except Exception:  # noqa: BLE001
            return False


def resolve_backend(identity: "str | None", open_spreadsheet=None,
                    shared_file_ok: bool = False):
    """Pick where this viewer's chats live. Returns (backend | None, note).

    - Signed in + a Sheet configured: that user's tab in the Sheet.
    - Signed in, no Sheet: a per-user file (survives refreshes, not a
      Streamlit Cloud redeploy).
    - Not signed in: the single shared file only when the owner opted in
      on a machine only they use (shared_file_ok); otherwise nothing is
      saved, because on a shared deployment one file would hand every
      visitor everyone else's chats.

    `open_spreadsheet` is a zero-argument callable returning a gspread
    Spreadsheet, or None when no Sheet is configured.
    """
    if identity:
        key = user_key(identity)
        if open_spreadsheet is not None:
            try:
                return SheetsBackend(open_spreadsheet(), key, "your Google Sheet tab"), ""
            except Exception as exc:  # noqa: BLE001
                return None, (f"Couldn't open the chat Google Sheet ({type(exc).__name__}); "
                              "chats won't be saved this session.")
        return FileBackend(os.path.join(USER_DIR, f"{key}.json"),
                           "this server's disk (cleared on redeploy)"), ""
    if shared_file_ok:
        return FileBackend(DEFAULT_PATH, "data/chat_history.json on this machine"), ""
    return None, ""
