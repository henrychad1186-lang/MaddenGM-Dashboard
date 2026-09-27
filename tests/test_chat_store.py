"""Tests for the GM Chat conversation store and game-log grounding."""

import json

import pandas as pd

from src import ai_gm, chat_store


def test_new_conversation_titled_from_first_question():
    store = {}
    conv = chat_store.new_conversation(store, "GB")
    chat_store.append_message(conv, "user", "Who should I trade for a pass rusher?")
    chat_store.append_message(conv, "assistant", "Target an EDGE.")
    chat_store.append_message(conv, "user", "Something else entirely")
    assert conv["title"] == "Who should I trade for a pass rusher?"
    assert len(conv["messages"]) == 3
    assert chat_store.get(store, "GB", conv["id"]) is conv


def test_long_title_cut_on_word_boundary():
    title = chat_store.make_title("word " * 30)
    assert title.endswith("…")
    assert len(title) <= 41
    assert "wor…" not in title


def test_conversations_are_per_team_and_newest_first():
    store = {}
    a = chat_store.new_conversation(store, "GB")
    b = chat_store.new_conversation(store, "GB")
    chat_store.new_conversation(store, "CHI")
    a["updated"], b["updated"] = 2, 1
    assert [c["id"] for c in chat_store.list_conversations(store, "GB")] == [a["id"], b["id"]]
    assert len(chat_store.list_conversations(store, "CHI")) == 1
    chat_store.delete_conversation(store, "GB", a["id"])
    assert [c["id"] for c in chat_store.list_conversations(store, "GB")] == [b["id"]]


def test_round_trip_through_disk(tmp_path):
    path = str(tmp_path / "sub" / "chats.json")
    store = {}
    conv = chat_store.new_conversation(store, "GB")
    chat_store.append_message(conv, "user", "hi")
    assert chat_store.save(store, path)
    assert chat_store.load(path) == store


def test_save_caps_conversation_count(tmp_path):
    path = str(tmp_path / "chats.json")
    store = {}
    for i in range(chat_store.MAX_CONVERSATIONS_PER_TEAM + 5):
        chat_store.new_conversation(store, "GB")["updated"] = i
    chat_store.save(store, path)
    kept = chat_store.load(path)["GB"]
    assert len(kept) == chat_store.MAX_CONVERSATIONS_PER_TEAM
    assert min(c["updated"] for c in kept) == 5  # oldest dropped


def test_missing_or_corrupt_file_loads_empty(tmp_path):
    assert chat_store.load(str(tmp_path / "nope.json")) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert chat_store.load(str(bad)) == {}
    bad.write_text(json.dumps(["a list"]))
    assert chat_store.load(str(bad)) == {}


def test_export_markdown_labels_speakers():
    conv = chat_store.new_conversation({}, "GB")
    chat_store.append_message(conv, "user", "Q?")
    chat_store.append_message(conv, "assistant", "A.")
    md = chat_store.export_markdown(conv, "GB")
    assert "**You:**" in md and "**AI GM:**" in md and md.startswith("# Q?")


def test_game_log_summary_record_close_games_and_playbooks():
    df = pd.DataFrame({
        "Opponent": ["CHI", "DET", "MIN"],
        "Result": ["WIN", "LOSS", "WIN"],
        "Points_For": [24, 17, 38],
        "Points_Against": [21, 20, 10],
        "Score_Diff": [3, -3, 28],
        "RZ_TD_Made": [2, 1, 4],
        "Playbook": ["West Coast", "West Coast", "Spread"],
    })
    text = ai_gm.build_game_log_summary(df)
    assert "record 2-1" in text
    assert "Close games (<= 8 pts): 1-1" in text
    assert "Spread: 1-0" in text and "West Coast: 1-1" in text
    assert "Red zone TDs/game: 2.3" in text
    assert "vs MIN: WIN 38-10" in text


def test_game_log_summary_handles_empty_and_sparse_logs():
    assert "no games" in ai_gm.build_game_log_summary(None)
    assert "no games" in ai_gm.build_game_log_summary(pd.DataFrame())
    text = ai_gm.build_game_log_summary(pd.DataFrame({"Result": ["WIN", "TIE"]}))
    assert "record 1-0-1" in text
