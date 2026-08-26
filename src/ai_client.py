"""
Optional Claude-powered scouting narratives for the AI GM Assistant.

The heuristic engine in `src.ai_gm` always runs first and produces the
grade, verdict, trade value, and strengths/weaknesses — those are
deterministic and grounded in the roster data. This module only asks
Claude to turn those *already-computed* facts into a punchier written
narrative; it's never given free rein to invent stats.

Falls back to `None` (heuristic blurb wins) whenever no API key is
configured, the `anthropic` package isn't installed, or the request fails
for any reason (network, rate limit, invalid key) — the app must never
break because of this being unavailable.
"""

import os
import re

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# The prompt asks for 3-4 sentences covering grade, strengths, weaknesses,
# and a verdict endorsement — that routinely runs past 300 tokens and gets
# cut off mid-sentence (confirmed against a live call: stop_reason was
# "max_tokens" at 300). 500 gives real headroom; _trim_to_last_sentence()
# below is the backstop for whatever still gets cut.
_MAX_TOKENS = 500

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
