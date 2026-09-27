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

import json
import os
import time
import uuid

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "chat_history.json")

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
    return {team: convs for team, convs in data.items() if isinstance(convs, list)}


def save(store: dict, path: str = DEFAULT_PATH) -> bool:
    """Write the store to disk atomically. Returns False if it couldn't."""
    trimmed = {
        team: sorted(convs, key=lambda c: c.get("updated", 0),
                     reverse=True)[:MAX_CONVERSATIONS_PER_TEAM]
        for team, convs in store.items()
    }
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
