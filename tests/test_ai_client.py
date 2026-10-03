"""Tests for the sentence-trimming helper used to clean up truncated Claude output."""

import json

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
    def __init__(self, chunks, stop_reason="end_turn", fail_after=None, content=None):
        self._chunks, self._stop, self._fail = chunks, stop_reason, fail_after
        self._content = content if content is not None else [
            _Block(type="text", text="".join(chunks))]

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
        return type("M", (), {"stop_reason": self._stop, "content": self._content})()


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


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



class _ScriptedClient:
    """Returns a queued stream per request and records each request."""

    def __init__(self, streams):
        self._streams, self.calls = list(streams), []
        outer = self

        class _M:
            def stream(self, **kw):
                # Snapshot: the loop keeps appending to the same list.
                outer.calls.append({**kw, "messages": list(kw["messages"])})
                return outer._streams.pop(0)

        self.messages = _M()


def _tool_ctx():
    from src import chat_tools, trade_engine
    return chat_tools.ToolContext(team="GB", rosters=trade_engine.DEMO_ROSTERS)


def _run_scripted(monkeypatch, streams, tool_ctx=None):
    from src import ai_client
    client = _ScriptedClient(streams)
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    out = "".join(ai_client.stream_gm_answer("q", "ctx", [], "GB", tool_ctx=tool_ctx))
    return out, client


def test_tool_call_runs_and_result_goes_back(monkeypatch):
    think = _Block(type="thinking", thinking="", signature="sig")
    use = _Block(type="tool_use", id="toolu_1", name="lookup_player",
                 input={"name": "Parsons"})
    out, client = _run_scripted(monkeypatch, [
        _FakeStream(["Checking. "], stop_reason="tool_use",
                    content=[think, _Block(type="text", text="Checking. "), use]),
        _FakeStream(["Parsons is untouchable."]),
    ], tool_ctx=_tool_ctx())
    assert "Looked up Parsons" in out and out.endswith("Parsons is untouchable.")
    assert len(client.calls) == 2
    assert client.calls[0]["tools"] and "trade engine" in client.calls[0]["system"]
    second = client.calls[1]["messages"]
    # Assistant turn replayed unchanged, thinking block first.
    assert second[-2]["role"] == "assistant" and second[-2]["content"][0] is think
    (result,) = second[-1]["content"]
    assert result["tool_use_id"] == "toolu_1" and "is_error" not in result
    assert json.loads(result["content"])["players"][0]["Name"] == "M. Parsons"


def test_parallel_calls_answered_in_one_message(monkeypatch):
    uses = [_Block(type="tool_use", id=f"t{i}", name="lookup_player", input={"name": n})
            for i, n in enumerate(["Parsons", "Nobody At All"])]
    _, client = _run_scripted(monkeypatch, [
        _FakeStream([], stop_reason="tool_use", content=uses),
        _FakeStream(["Done."]),
    ], tool_ctx=_tool_ctx())
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t0", "t1"]
    assert "is_error" not in results[0] and results[1]["is_error"] is True


def test_invalid_tool_input_is_an_error_result_not_a_crash(monkeypatch):
    use = _Block(type="tool_use", id="t", name="evaluate_trade", input={"offer": "x"})
    out, client = _run_scripted(monkeypatch, [
        _FakeStream([], stop_reason="tool_use", content=[use]),
        _FakeStream(["Need names."]),
    ], tool_ctx=_tool_ctx())
    (result,) = client.calls[1]["messages"][-1]["content"]
    assert result["is_error"] is True and "list of player names" in result["content"]
    assert out.endswith("Need names.")


def test_truncated_tool_call_is_never_run(monkeypatch):
    use = _Block(type="tool_use", id="t", name="lookup_player", input={"name": "Par"})
    out, client = _run_scripted(monkeypatch, [
        _FakeStream([], stop_reason="max_tokens", content=[use]),
    ], tool_ctx=_tool_ctx())
    assert len(client.calls) == 1 and "truncated" in out and "Looked up" not in out


def test_refusal_stops_the_loop(monkeypatch):
    out, client = _run_scripted(monkeypatch, [_FakeStream([], stop_reason="refusal", content=[])],
                                tool_ctx=_tool_ctx())
    assert "declined" in out and len(client.calls) == 1


def test_runaway_loop_is_capped(monkeypatch):
    from src import ai_client
    n = ai_client._MAX_TOOL_ROUNDS + 1
    streams = [_FakeStream([], stop_reason="tool_use",
                           content=[_Block(type="tool_use", id=f"t{i}", name="lookup_player",
                                           input={"name": "Parsons"})]) for i in range(n)]
    streams.append(_FakeStream(["OK."]))
    out, client = _run_scripted(monkeypatch, streams, tool_ctx=_tool_ctx())
    last = json.loads(client.calls[-1]["messages"][-1]["content"][0]["content"])
    assert "budget" in last["error"] and out.endswith("OK.")


def test_no_tools_sent_without_a_context(monkeypatch):
    _, client = _run_scripted(monkeypatch, [_FakeStream(["Hi."])])
    assert "tools" not in client.calls[0]
