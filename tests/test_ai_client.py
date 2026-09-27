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


class _FakeStream:
    def __init__(self, chunks, stop_reason="end_turn", fail_after=None):
        self._chunks, self._stop, self._fail = chunks, stop_reason, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        for i, c in enumerate(self._chunks):
            if self._fail is not None and i == self._fail:
                raise RuntimeError("network down")
            yield c

    def get_final_message(self):
        return type("M", (), {"stop_reason": self._stop})()


def _fake_client(stream):
    messages = type("Msgs", (), {"stream": lambda self, **kw: stream})()
    return type("C", (), {"messages": messages})()


def _run(monkeypatch, stream):
    from src import ai_client
    monkeypatch.setattr(ai_client, "_get_client", lambda: _fake_client(stream))
    return "".join(ai_client.stream_gm_answer("q", "ctx", [], "GB"))


def test_stream_yields_chunks(monkeypatch):
    assert _run(monkeypatch, _FakeStream(["Trade ", "for an EDGE."])) == "Trade for an EDGE."


def test_stream_flags_truncation(monkeypatch):
    out = _run(monkeypatch, _FakeStream(["Long answer"], stop_reason="max_tokens"))
    assert out.startswith("Long answer") and "truncated" in out


def test_stream_failure_mid_answer_is_marked_incomplete(monkeypatch):
    out = _run(monkeypatch, _FakeStream(["Half ", "never"], fail_after=1))
    assert out.startswith("Half ") and "incomplete" in out


def test_stream_failure_before_text_gives_error_message(monkeypatch):
    from src import ai_client
    assert _run(monkeypatch, _FakeStream(["x"], fail_after=0)) == ai_client.CHAT_ERROR_MESSAGE
    monkeypatch.setattr(ai_client, "_get_client", lambda: None)
    assert "".join(ai_client.stream_gm_answer("q", "c", [], "GB")) == ai_client.CHAT_ERROR_MESSAGE
