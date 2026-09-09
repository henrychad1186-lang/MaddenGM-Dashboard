"""Tests for the sentence-trimming helper used to clean up truncated Claude output."""

from src.ai_client import _trim_to_last_sentence


def test_trims_dangling_fragment_after_last_complete_sentence():
    text = "He runs a clean route. He shows good hands and"
    assert _trim_to_last_sentence(text) == "He runs a clean route."


def test_end_of_string_period_is_not_treated_as_a_boundary():
    # Truncation landed right after "4." (about to continue "4.4 forty") —
    # the trailing period must not be mistaken for a real sentence end.
    text = "He is explosive and clocks a 4."
    assert _trim_to_last_sentence(text) == ""


def test_returns_empty_string_when_no_punctuation_found():
    text = "He is explosive and shows great burst off the line"
    assert _trim_to_last_sentence(text) == ""


def test_keeps_multiple_complete_sentences():
    text = "He is fast. He is strong. He is still"
    assert _trim_to_last_sentence(text) == "He is fast. He is strong."
