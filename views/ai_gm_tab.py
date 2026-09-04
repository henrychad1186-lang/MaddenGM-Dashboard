"""
AI GM Assistant tab — scout and add players, then ask questions about them.

Players added here live in `st.session_state`, never in the module-level
rosters, so one visitor's additions stay out of every other visitor's
view. They reach the rest of the app as `ctx.extra_players`.
"""

import streamlit as st

from src import ai_client, ai_gm
from views import theme
from views.cache import cached_positional_needs
from views.context import AppContext

# How many past turns of chat to resend as context. Caps prompt growth
# over a long session while keeping enough for follow-up questions.
_CHAT_HISTORY_TURNS = 12

_AI_UNAVAILABLE_MESSAGE = (
    "Sorry — I couldn't reach Claude just now. Please try again in a moment.")


def _init_state() -> None:
    st.session_state.setdefault("ai_gm_log", [])
    st.session_state.setdefault("ai_gm_form_version", 0)
    st.session_state.setdefault("ai_gm_chat", [])


def _render_status_badge() -> None:
    if ai_client.is_available():
        st.markdown('<span style="background:#00e67620; color:#00e676; '
                    'padding:3px 10px; border-radius:20px; font-size:0.78rem; '
                    'font-weight:700; border:1px solid #00e67650;">'
                    '🟢 Live Claude scouting narratives</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span style="background:#ffffff10; color:#94a3b8; '
                    'padding:3px 10px; border-radius:20px; font-size:0.78rem; '
                    'font-weight:600; border:1px solid #ffffff20;">'
                    '⚪ Heuristic scouting (set ANTHROPIC_API_KEY for live Claude writeups)</span>',
                    unsafe_allow_html=True)


def _render_add_player_form() -> "tuple[bool, dict, bool]":
    """Draw the scouting form. Returns (submitted, player dict, persist flag)."""
    # Keying the form on a version counter (bumped only after a successful
    # add) resets the fields for the next entry without wiping them out
    # from under a failed validation.
    form_key = f"ai_gm_add_player_form_{st.session_state.ai_gm_form_version}"
    with st.form(form_key, clear_on_submit=False):
        name = st.text_input("Name", placeholder="e.g. J. Smith")
        c1, c2, c3 = st.columns(3)
        with c1:
            pos = st.selectbox("Position", ai_gm.SCOUTABLE_POSITIONS)
        with c2:
            age = st.number_input("Age", min_value=18, max_value=45, value=22)
        with c3:
            ovr = st.number_input("OVR", min_value=1, max_value=99, value=70)

        dev = st.selectbox("Dev Trait", ai_gm.DEV_TRAITS)

        st.caption("Physical attributes (optional — powers the AI scouting read)")
        a1, a2, a3 = st.columns(3)
        with a1:
            spd = st.slider("SPD", 0, 99, 80)
            cod = st.slider("COD", 0, 99, 80)
        with a2:
            acc = st.slider("ACC", 0, 99, 80)
            strength = st.slider("STR", 0, 99, 70)
        with a3:
            agi = st.slider("AGI", 0, 99, 80)
            awr = st.slider("AWR", 0, 99, 70)

        cc1, cc2 = st.columns(2)
        with cc1:
            savings = st.text_input("Cap Savings", value="$0")
        with cc2:
            penalty = st.text_input("Dead Cap Penalty", value="$0")

        persist = st.checkbox(
            "💾 Save to roster CSV (persists across restarts)", value=False)

        submitted = st.form_submit_button(
            "🔮 Scout & Add to Roster", use_container_width=True)

    return submitted, {
        "Name": name, "Pos": pos, "Age": age, "OVR": ovr, "Dev": dev,
        "SPD": spd, "ACC": acc, "AGI": agi, "COD": cod, "STR": strength,
        "AWR": awr, "Savings": savings, "Penalty": penalty,
    }, persist


def _scout_and_add(new_player: dict, persist: bool, ctx: AppContext) -> None:
    result = ai_gm.add_player(new_player, ctx.my_team)
    if not result["ok"]:
        for error in result["errors"]:
            st.error(error)
        return

    report = ai_gm.scout_player(result["player"], ctx.my_team, ctx.extra_players)

    # The verdict/grade/trade-value above are always the deterministic
    # heuristic output. If a Claude API key is configured, ask it to
    # rewrite just the narrative blurb grounded in those already-computed
    # facts; otherwise the templated heuristic blurb stands as-is.
    report["ai_generated"] = False
    if ai_client.is_available():
        with st.spinner("Consulting AI GM..."):
            blurb = ai_client.generate_scouting_narrative(
                result["player"], report, ctx.my_team)
        if blurb:
            report["blurb"] = blurb
            report["ai_generated"] = True
        else:
            st.warning("Claude request failed — showing heuristic scouting "
                       "report instead.")

    st.session_state.ai_gm_players.append(result["player"])
    st.session_state.ai_gm_log.insert(0, report)
    if persist:
        ai_gm.persist_roster(ctx.my_team, st.session_state.ai_gm_players)
    st.session_state.ai_gm_form_version += 1
    st.success(f"✅ **{result['player']['Name']}** added to the "
               f"{ctx.my_team} roster.")
    st.rerun()


def _render_needs_board(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 🧭 Positional Needs Board")
    st.caption("AI-computed depth + quality grade per position — use this to "
               "decide who to scout next.")
    cols = st.columns(4)
    for i, n in enumerate(cached_positional_needs(ctx.my_team, ctx.extra_players)):
        with cols[i % 4]:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(30,30,60,0.9), rgba(50,50,80,0.7));
                border: 1px solid {n['color']}40; border-left: 4px solid {n['color']};
                border-radius: 12px; padding: 0.7rem; margin-bottom: 0.6rem; text-align:center;">
                <div style="font-weight:800; color:white;">{n['pos']}</div>
                <div style="color:{n['color']}; font-weight:700; font-size:0.85rem;">{n['level']}</div>
                <div style="color:#888; font-size:0.72rem;">{n['count']} plyr · {n['avg_ovr']:.0f} avg</div>
            </div>
            """, unsafe_allow_html=True)


def _render_report_card(report: dict, ctx: AppContext) -> None:
    vc = report["verdict_color"]
    source_badge = (
        '<span style="color:#a78bfa; font-size:0.7rem; font-weight:700;">✨ Claude</span>'
        if report.get("ai_generated") else
        '<span style="color:#64748b; font-size:0.7rem;">⚙️ Heuristic</span>')
    st.markdown(f"""
    <div class="trade-card" style="border-left: 4px solid {vc};">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:1.15rem; font-weight:800; color:#f1f5f9;">
                {report['Name']} <span style="color:#94a3b8; font-weight:500; font-size:0.85rem;">
                {report['Pos']} · {report['Age']}yo · {report['OVR']} OVR</span>
            </span>
            <span style="background:{vc}; color:#000; font-weight:800; padding:2px 10px;
                border-radius:8px; font-size:0.75rem; white-space:nowrap;">{report['verdict']}</span>
        </div>
        <div style="color:#cbd5e1; font-size:0.85rem; margin-top:8px; line-height:1.5;">{report['blurb']}</div>
        <div style="margin-top:6px;">{source_badge}</div>
    </div>
    """, unsafe_allow_html=True)

    remove_col, regen_col = st.columns(2)
    with remove_col:
        if st.button("🗑️ Remove", key=f"ai_gm_remove_{report['_id']}",
                     use_container_width=True):
            st.session_state.ai_gm_players = ai_gm.remove_from_list(
                st.session_state.ai_gm_players, report["_id"])
            st.session_state.ai_gm_log = [
                r for r in st.session_state.ai_gm_log
                if r["_id"] != report["_id"]]
            st.rerun()
    with regen_col:
        # Regenerating a heuristic blurb would just reproduce the same
        # deterministic text — only worth offering when Claude is actually
        # writing the narrative.
        if not ai_client.is_available():
            return
        if st.button("🔄 Regenerate", key=f"ai_gm_regen_{report['_id']}",
                     use_container_width=True):
            source_player = next(
                (p for p in st.session_state.ai_gm_players
                 if p["_id"] == report["_id"]), None)
            if source_player is not None:
                with st.spinner("Asking Claude for a fresh take..."):
                    blurb = ai_client.generate_scouting_narrative(
                        source_player, report, ctx.my_team)
                if blurb:
                    report["blurb"] = blurb
                    report["ai_generated"] = True
                else:
                    st.warning("Regeneration failed — keeping the previous version.")
            st.rerun()


def _ask(question: str, ctx: AppContext, history: "list[dict]") -> str:
    context_summary = ai_gm.build_context_summary(ctx.my_team, ctx.extra_players)
    answer = ai_client.answer_gm_question(
        question, context_summary, history, ctx.my_team)
    return answer if answer is not None else _AI_UNAVAILABLE_MESSAGE


def _render_chat(ctx: AppContext) -> None:
    st.markdown("---")
    st.markdown("#### 💬 Ask the AI GM")
    st.caption("Ask anything about your roster, cap situation, trade targets, or "
               "needs — every answer is grounded in your actual data below, not "
               "a generic guess.")

    # Stale chat referencing a different team's data would be misleading —
    # reset on team switch rather than let old answers linger.
    if st.session_state.get("ai_gm_chat_team") != ctx.my_team:
        st.session_state.ai_gm_chat = []
        st.session_state.ai_gm_chat_team = ctx.my_team

    if not ai_client.is_available():
        st.info("💬 Chat requires a live Claude connection — set `ANTHROPIC_API_KEY` "
                "(env var locally, or Streamlit Cloud Settings → Secrets) to unlock it. "
                "The scouting reports above still work either way.")
        return

    for msg in st.session_state.ai_gm_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.ai_gm_chat:
        clear_col, regen_col = st.columns(2)
        with clear_col:
            if st.button("🗑️ Clear chat", key="ai_gm_chat_clear",
                         use_container_width=True):
                st.session_state.ai_gm_chat = []
                st.rerun()
        with regen_col:
            last = st.session_state.ai_gm_chat[-1]
            if last["role"] == "assistant" and st.button(
                    "🔄 Regenerate last answer", key="ai_gm_chat_regen",
                    use_container_width=True):
                st.session_state.ai_gm_chat.pop()  # drop the stale answer
                question = st.session_state.ai_gm_chat[-1]["content"]
                history = st.session_state.ai_gm_chat[:-1][-_CHAT_HISTORY_TURNS:]
                with st.spinner("Asking again..."):
                    answer = _ask(question, ctx, history)
                st.session_state.ai_gm_chat.append(
                    {"role": "assistant", "content": answer})
                st.rerun()

    if prompt := st.chat_input("e.g. Who should I trade for a pass rusher?"):
        st.session_state.ai_gm_chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Consulting the AI GM..."):
                # Exclude the prompt just appended — _ask takes it
                # separately — and cap history so the prompt doesn't grow
                # unbounded over a long session.
                history = st.session_state.ai_gm_chat[:-1][-_CHAT_HISTORY_TURNS:]
                answer = _ask(prompt, ctx, history)
            st.markdown(answer)
        st.session_state.ai_gm_chat.append(
            {"role": "assistant", "content": answer})


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "🤖", "AI GM Assistant",
        f"Scout a draft pick, UDFA, or trade target — plug them into the "
        f"{ctx.my_team} roster and get an instant AI grade")

    _render_status_badge()
    _init_state()

    col_form, col_reports = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown("#### ➕ Scout & Add a Player")
        submitted, new_player, persist = _render_add_player_form()
        if submitted:
            _scout_and_add(new_player, persist, ctx)
        _render_needs_board(ctx)

    with col_reports:
        st.markdown("#### 📋 AI Scouting Reports")
        if not st.session_state.ai_gm_log:
            st.info("Add a player on the left to generate an AI scouting report.")
        else:
            for report in st.session_state.ai_gm_log:
                _render_report_card(report, ctx)

    _render_chat(ctx)
