"""
Optional Claude-powered features for the AI GM Assistant: scouting
narratives for a single player, and free-form chat over the team's data.

The heuristic engine in `src.ai_gm` always runs first for scouting and
produces the grade, verdict, trade value, and strengths/weaknesses —
those are deterministic and grounded in the roster data. This module
only asks Claude to turn those *already-computed* facts into a punchier
written narrative; it's never given free rein to invent stats. The chat
feature has no non-Claude equivalent (open-ended Q&A isn't something a
rules engine can answer), so it's simply unavailable rather than
degraded when no key is configured — but every answer is still grounded
in a text snapshot of the real roster/cap/needs data, not invented.

Both features fall back to `None` (or, for chat, are hidden by the
caller) whenever no API key is configured, the `anthropic` package isn't
installed, or the request fails for any reason (network, rate limit,
invalid key) — the app must never break because of this being
unavailable.
"""

import json
import os
import re

# Current-generation Sonnet (same per-token price as claude-sonnet-5).
_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
# Sonnet 5.x runs adaptive thinking by default, and thinking tokens count
# against max_tokens. The old 500 budget (sized for ~4 sentences of visible
# text) could be spent before any text arrived. Low effort keeps thinking
# short for these grounded, short-form answers; the larger ceilings are
# headroom, not a target. _trim_to_last_sentence() stays the backstop.
_OUTPUT_CONFIG = {"effort": "low"}


def _effort_kwargs() -> dict:
    """`output_config` for models that accept `effort`, else nothing.

    Haiku 4.5 and pre-4.6 Sonnets 400 on `effort`, and every failure here
    is swallowed into "Claude unavailable" — so an ANTHROPIC_MODEL
    override to one of them would silently disable the AI features.
    """
    if "haiku" in _MODEL or re.search(r"-(3|4-[015])(-|$)", _MODEL):
        return {}
    return {"output_config": _OUTPUT_CONFIG}
_MAX_TOKENS = 2000

_client = None
_client_checked = False


def _get_client():
    """Lazily build (and cache) an Anthropic client if a key is configured."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        return None

    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        _client = None
    return _client


def is_available() -> bool:
    """True if a usable Anthropic client could be built (key + package present)."""
    return _get_client() is not None


def _build_prompt(player: dict, report: dict, team: str) -> str:
    def attr(key):
        val = player.get(key)
        return val if val not in (None, "") else "unknown"

    return f"""You are an NFL front-office scout writing a short scouting
report for a Madden 27 franchise GM tool. Use ONLY the facts given below —
do not invent stats, injuries, or backstory that isn't provided.

Player: {player.get('Name')}
Position: {report['Pos']}
Age: {report['Age']}
Overall: {report['OVR']} ({report['tier']})
Dev Trait: {report['Dev']}
Attributes: SPD {attr('SPD')}, ACC {attr('ACC')}, AGI {attr('AGI')}, COD {attr('COD')}, STR {attr('STR')}, AWR {attr('AWR')}
Team: {team}
Position room grade: {report['need_level']} ({report['pos_count']} players, {report['pos_avg_ovr']} avg OVR)
Computed trade value: {report['trade_value']}
Computed verdict: {report['verdict']} — {report['reason']}

Write 3-4 sentences: an overall grade/comp, athletic strengths and
weaknesses drawn strictly from the attributes above, and close by
explicitly endorsing the given verdict with your own reasoning. Scouting-
report voice — direct, opinionated, no hedging, no markdown headers."""


_SENTENCE_END_RE = re.compile(r'[.!?](?:["\')\]]*)(?=\s)')


def _trim_to_last_sentence(text: str) -> str:
    """Only called when generation was cut off mid-stream, so the very end
    of `text` is where it got cut, never a real sentence boundary — trim
    back to the last complete sentence, or "" if none exists."""
    matches = list(_SENTENCE_END_RE.finditer(text))
    if not matches:
        return ""
    return text[:matches[-1].end()].strip()


def generate_scouting_narrative(player: dict, report: dict, team: str) -> "str | None":
    """Ask Claude to write a scouting narrative grounded in computed stats.

    Returns None if no key is configured or the call fails — callers
    should fall back to the deterministic `report["blurb"]` in that case.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            **_effort_kwargs(),
            messages=[{"role": "user", "content": _build_prompt(player, report, team)}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            return None
        if resp.stop_reason == "max_tokens":
            text = _trim_to_last_sentence(text)
        return text or None
    except Exception:
        return None


# The dedicated chat tab invites longer comparative questions ("rank my
# three worst contracts and who replaces each") than the old inline box
# did; 600 cut those off. Streaming makes the longer wait invisible, and
# the budget is shared with thinking (see _MAX_TOKENS).
_CHAT_MAX_TOKENS = 4000
_CHAT_SYSTEM_PROMPT = """You are the AI GM Assistant for a Madden 27 franchise \
dashboard, answering the user's questions about their team, {team}. Base every \
answer strictly on the data below — never invent a player, stat, contract, or \
grade that isn't in it. If the data doesn't support an answer, say so plainly \
instead of guessing. Keep answers focused and actionable in a direct GM voice — \
a short paragraph or a short list, not an essay. No markdown headers.

CURRENT TEAM DATA:
{context_summary}"""


def answer_gm_question(question: str, context_summary: str,
                       history: "list[dict]", team: str) -> "str | None":
    """Answer a free-form GM question grounded in a text snapshot of the
    team's real roster/cap/needs data (see `src.ai_gm.build_context_summary`).

    `history` is prior turns as [{"role": "user"|"assistant", "content": str}, ...],
    NOT including `question` itself — that's appended here. Returns None if
    no key is configured or the request fails; there's no non-Claude
    fallback for open-ended chat, so callers should hide the chat UI
    entirely when `is_available()` is False rather than call this.
    """
    client = _get_client()
    if client is None:
        return None

    messages = list(history) + [{"role": "user", "content": question}]

    try:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=_CHAT_MAX_TOKENS,
            **_effort_kwargs(),
            system=_CHAT_SYSTEM_PROMPT.format(team=team, context_summary=context_summary),
            messages=messages,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            return None
        if resp.stop_reason == "max_tokens":
            text = _trim_to_last_sentence(text)
        return text or None
    except Exception:
        return None


CHAT_ERROR_MESSAGE = ("Sorry — I couldn't reach Claude just now. "
                      "Please try again in a moment.")


# A question can take several lookups ("compare these three EDGEs, then
# price the best one"), but a runaway loop spends tokens and makes the
# user wait. Past this, the model is told to answer with what it has.
_MAX_TOOL_ROUNDS = 6

_TOOLS_PROMPT = """

You also have tools that call this dashboard's own trade engine: player \
lookup (ratings, trade value, verdict, cap hit), trade targets by position, \
trade evaluation with a draft-pick counter-offer, and trade-partner search. \
Use them whenever an answer depends on a trade value, a trade verdict, a \
player on another team, or a cap figure for a specific player — don't \
estimate those from the snapshot. Only DET, CHI and MIN are modeled as \
trade partners; say so if the user asks about another team."""


def stream_gm_answer(question: str, context_summary: str,
                     history: "list[dict]", team: str, tool_ctx=None):
    """Streaming version of `answer_gm_question`, for `st.write_stream`.

    Yields text chunks as Claude produces them. With `tool_ctx` (a
    `src.chat_tools.ToolContext`), Claude may call the trade-engine tools
    mid-answer; each call is announced with a short italic line so the
    user can see what was looked up, and the loop continues until Claude
    answers or `_MAX_TOOL_ROUNDS` is reached.

    Never raises: a missing client or a failure before any text arrived
    yields `CHAT_ERROR_MESSAGE`; a failure mid-answer appends a short
    note so a half answer isn't mistaken for a complete one.
    """
    client = _get_client()
    if client is None:
        yield CHAT_ERROR_MESSAGE
        return

    from src import chat_tools  # local: keeps this module importable alone

    system = _CHAT_SYSTEM_PROMPT.format(team=team, context_summary=context_summary)
    tool_kwargs = {}
    if tool_ctx is not None:
        system += _TOOLS_PROMPT
        tool_kwargs = {"tools": chat_tools.TOOL_DEFINITIONS}

    messages = list(history) + [{"role": "user", "content": question}]
    produced = False
    rounds = 0
    try:
        while True:
            with client.messages.stream(
                model=_MODEL,
                max_tokens=_CHAT_MAX_TOKENS,
                **_effort_kwargs(),
                system=system,
                messages=messages,
                **tool_kwargs,
            ) as stream:
                for chunk in stream.text_stream:
                    if chunk:
                        produced = True
                        yield chunk
                final = stream.get_final_message()

            if final.stop_reason == "refusal":
                yield ("\n\n_(Claude declined to answer this one — try "
                       "rephrasing the question.)_")
                return
            tool_uses = [b for b in final.content if getattr(b, "type", "") == "tool_use"]
            if final.stop_reason == "max_tokens":
                # A tool_use cut off here parses as a plausible partial
                # input, so never run it.
                yield "\n\n_(answer truncated — ask me to continue)_"
                return
            if final.stop_reason != "tool_use" or not tool_uses:
                break

            rounds += 1
            # Append the whole assistant turn unchanged (thinking blocks
            # included) so the history stays append-only.
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for block in tool_uses:
                label = chat_tools.describe(block.name, block.input)
                yield f"\n\n_🔎 {label[:1].upper() + label[1:]}…_\n\n"
                produced = True
                if rounds > _MAX_TOOL_ROUNDS:
                    out = {"error": "Tool budget for this answer is used up. "
                                    "Answer with what you have."}
                else:
                    out = chat_tools.run(tool_ctx, block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out),
                    **({"is_error": True} if "error" in out else {}),
                })
            # All results for this turn go back in one user message.
            messages.append({"role": "user", "content": results})
    except Exception:
        yield ("\n\n_(connection lost — answer incomplete)_"
               if produced else CHAT_ERROR_MESSAGE)
        return
    if not produced:
        yield CHAT_ERROR_MESSAGE
