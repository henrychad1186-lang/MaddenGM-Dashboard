"""Trade Machine tab — player scout, interested teams, trade evaluator."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.trade_engine import evaluate_trade, get_trade_value
from views import theme
from views.cache import cached_trade_partners
from views.context import AppContext

_DEV_COLORS = {"Superstar X": "#f59e0b", "Superstar": "#a78bfa",
               "Star": "#60a5fa", "Normal": "#94a3b8"}

_SPOTLIGHT_ATTRS = [("SPD", "SPD"), ("ACC", "ACC"), ("AGI", "AGI"),
                    ("STR", "STR"), ("AWR", "AWR"), ("COD", "COD")]

_RADAR_ATTRS = [("SPD", "Speed"), ("ACC", "Accel"), ("AGI", "Agility"),
                ("COD", "CoD"), ("STR", "Strength"), ("AWR", "Aware")]


def _has_value(val) -> bool:
    """True when an attribute is actually filled in (not blank, not NaN)."""
    if val is None or str(val).strip() == "":
        return False
    return not (isinstance(val, float) and np.isnan(val))


def _ovr_color(ovr: int) -> str:
    if ovr >= 90:
        return "#00e676"
    if ovr >= 80:
        return "#2196f3"
    if ovr >= 70:
        return "#ffc107"
    return "#ff5252"


def _render_spotlight(player: dict, player_value: float) -> None:
    dev_c = _DEV_COLORS.get(str(player.get("Dev", "Normal")), "#94a3b8")
    ovr_val = int(player.get("OVR", 70))
    ovr_c = _ovr_color(ovr_val)

    pills_html = "".join(
        f'<span class="stat-pill">{label} {int(player[key])}</span>'
        for key, label in _SPOTLIGHT_ATTRS
        if _has_value(player.get(key))
    )

    contract_html = ""
    savings = player.get("Savings", "")
    penalty = player.get("Penalty", "")
    if savings and str(savings).strip():
        contract_html += f'<span class="stat-pill">💰 Cap Savings: {savings}</span>'
    if penalty and str(penalty).strip():
        contract_html += f'<span class="stat-pill">⚠️ Dead Cap: {penalty}</span>'

    st.markdown(f"""
    <div class="player-spotlight">
        <div style="position:relative; z-index:1;">
            <div style="font-size:3rem; font-weight:900; color:{ovr_c};
                        text-shadow: 0 0 20px {ovr_c}40;">{ovr_val}</div>
            <div style="font-size:0.8rem; color:#64748b; text-transform:uppercase;
                        letter-spacing:2px;">OVERALL</div>
            <div style="font-size:1.6rem; font-weight:700; color:#f1f5f9;
                        margin-top:8px;">{player['Name']}</div>
            <div style="margin-top:4px;">
                <span style="background:{dev_c}20; color:{dev_c}; padding:4px 12px;
                            border-radius:20px; font-size:0.8rem; font-weight:600;
                            border: 1px solid {dev_c}50;">
                    {player.get('Dev', 'Normal')}
                </span>
                <span style="color:#94a3b8; margin:0 8px;">·</span>
                <span style="color:#cbd5e1;">{player['Pos']}</span>
                <span style="color:#94a3b8; margin:0 8px;">·</span>
                <span style="color:#cbd5e1;">Age {int(player.get('Age', 0))}</span>
            </div>
            <div style="margin-top:12px;">{pills_html}</div>
            <div style="margin-top:6px;">{contract_html}</div>
            <div style="margin-top:16px; font-size:1.8rem; font-weight:800;
                        background: linear-gradient(90deg, #6366f1, #10b981);
                        -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                {player_value:,.0f}
                <span style="font-size:0.7rem; -webkit-text-fill-color: #64748b;
                            font-weight:400;"> TRADE VALUE</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_radar(player: dict) -> None:
    labels, values = [], []
    for key, label in _RADAR_ATTRS:
        if _has_value(player.get(key)):
            labels.append(label)
            values.append(int(player[key]))

    if len(labels) < 3:
        st.caption("📊 _Radar chart available when SPD/ACC/AGI data is filled in._")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=labels + [labels[0]],
        fill='toself',
        fillcolor='rgba(99, 102, 241, 0.2)',
        line=dict(color='#6366f1', width=2),
        marker=dict(size=6, color='#a5b4fc'),
        name=player['Name'],
    ))
    fig.update_layout(
        polar=dict(
            bgcolor='rgba(0,0,0,0)',
            radialaxis=dict(visible=True, range=[40, 100],
                            gridcolor='rgba(148,163,184,0.15)',
                            tickfont=dict(size=9, color='#64748b')),
            angularaxis=dict(gridcolor='rgba(148,163,184,0.15)',
                             tickfont=dict(size=11, color='#cbd5e1')),
        ),
        showlegend=False,
        margin=dict(l=40, r=40, t=30, b=30),
        height=280,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_partners(player: dict, my_team: str) -> None:
    theme.divider()
    st.markdown("#### 🎯 Interested Teams")
    for p in cached_trade_partners(player, my_team):
        fit_badge = (' <span style="color:#10b981; font-size:0.75rem;">✅ SCHEME FIT</span>'
                     if p["scheme_fit"] else "")
        interest = p["interest"]
        bar_color = ("#10b981" if interest >= 70
                     else "#f59e0b" if interest >= 40 else "#ef4444")

        st.markdown(f"""
        <div class="trade-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:1.1rem; font-weight:700; color:#f1f5f9;">{p['team']}</span>
                <span style="color:{bar_color}; font-weight:700;">{interest}%{fit_badge}</span>
            </div>
            <div class="interest-bar">
                <div class="interest-fill" style="width:{interest}%; background: linear-gradient(90deg, {bar_color}, {bar_color}aa);"></div>
            </div>
            <div style="color:#94a3b8; font-size:0.85rem; margin-bottom:4px;">↳ {p['reason']}</div>
            <div style="color:#cbd5e1; font-size:0.9rem;">Best offer: <strong>{p['best_offer_name']}</strong>
                <span style="color:#64748b;">({p['best_offer_pos']}, {p['best_offer_ovr']} OVR)</span></div>
        </div>
        """, unsafe_allow_html=True)


def _render_evaluation(result: dict) -> None:
    if "ACCEPTED" in result["verdict"]:
        badge_class = "verdict-accept"
    elif "LEAN" in result["verdict"]:
        badge_class = "verdict-lean"
    else:
        badge_class = "verdict-decline"

    st.markdown(f'<div class="{badge_class}">{result["verdict"]}</div>',
                unsafe_allow_html=True)
    st.markdown("")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Their Side", "Your Offer"],
        x=[result["requested_value"], result["offered_value"]],
        orientation='h',
        marker=dict(color=['#ef4444', '#10b981'], line=dict(width=0)),
        text=[f"{result['requested_value']:,.0f}",
              f"{result['offered_value']:,.0f}"],
        textposition='inside',
        textfont=dict(size=14, color='white', family='Arial Black'),
    ))
    fig.update_layout(
        height=140,
        margin=dict(l=0, r=20, t=10, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(visible=False),
        yaxis=dict(tickfont=dict(size=12, color='#cbd5e1'),
                   gridcolor='rgba(0,0,0,0)'),
        bargap=0.35,
    )
    st.plotly_chart(fig, use_container_width=True)

    diff = result["diff"]
    diff_label = (f"+{diff:,.0f} in your favor" if diff > 0
                  else f"{diff:,.0f} gap to close")
    diff_color = "#10b981" if diff >= 0 else "#f59e0b"
    st.markdown(f'<div style="text-align:center; color:{diff_color}; '
                f'font-weight:700; font-size:1.1rem;">'
                f'{diff_label}</div>', unsafe_allow_html=True)

    if result["counter_offer"]:
        st.markdown("")
        st.markdown(f"""
        <div class="trade-card" style="border-color: rgba(245,158,11,0.4);">
            <div style="color:#f59e0b; font-weight:700; margin-bottom:6px;">💡 GM Suggestion</div>
            <div style="color:#e2e8f0;">{result['counter_offer']}</div>
        </div>
        """, unsafe_allow_html=True)


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "🏈", "War Room 2.0",
        "Find trade partners · Evaluate deals · AI counter-offers")

    col_scout, col_eval = st.columns([1, 1], gap="large")

    # ── LEFT — Player Scout & Partner Finder ──
    with col_scout:
        st.markdown("#### 🔍 Player Scout")
        user_roster = ctx.effective_trade_rosters[
            ctx.effective_trade_rosters["Team"] == ctx.my_team].copy()
        selected_name = st.selectbox(
            "Select a player to shop:", user_roster["Name"].tolist(),
            key="trade_player_select")

        selected_player = user_roster[
            user_roster["Name"] == selected_name].iloc[0].to_dict()

        _render_spotlight(selected_player, get_trade_value(selected_player))
        _render_radar(selected_player)
        _render_partners(selected_player, ctx.my_team)

    # ── RIGHT — Trade Evaluator ──
    with col_eval:
        st.markdown("#### ⚖️ Trade Evaluator")
        st.markdown('<p style="color:#94a3b8;">Build a trade and see if the CPU accepts.</p>',
                    unsafe_allow_html=True)

        st.markdown('<div class="trade-card">', unsafe_allow_html=True)
        st.markdown("**🟢 You Send:**")
        offer_names = st.multiselect(
            "Players to offer:",
            user_roster["Name"].tolist(),
            default=[selected_name],
            key="trade_offer_select",
        )
        offered = [
            user_roster[user_roster["Name"] == n].iloc[0].to_dict()
            for n in offer_names
            if n in user_roster["Name"].values
        ]
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="trade-card">', unsafe_allow_html=True)
        st.markdown("**🔴 You Receive:**")
        cpu_team = st.selectbox(
            "From team:",
            [t for t in ctx.trade_rosters["Team"].unique() if t != ctx.my_team],
            key="trade_cpu_team",
        )
        cpu_roster = ctx.trade_rosters[ctx.trade_rosters["Team"] == cpu_team]
        request_names = st.multiselect(
            "Players to request:",
            cpu_roster["Name"].tolist(),
            key="trade_request_select",
        )
        requested = [
            cpu_roster[cpu_roster["Name"] == n].iloc[0].to_dict()
            for n in request_names
            if n in cpu_roster["Name"].values
        ]
        st.markdown('</div>', unsafe_allow_html=True)

        if st.button("📋 Evaluate Trade", key="eval_trade_btn",
                     use_container_width=True):
            if not offered or not requested:
                st.warning("Select at least one player on each side.")
            else:
                _render_evaluation(evaluate_trade(offered, requested))
