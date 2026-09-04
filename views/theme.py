"""
Global look and feel: the dark-theme stylesheet plus the small HTML
builders every tab shares.

Extracted verbatim from the top of the old monolithic `app.py`. Keeping
the CSS in one place means a tab module never has to know what a
`.trade-card` or `.kpi-card` looks like — it just uses the class.
"""

import streamlit as st

_CSS = """\
<style>
:root {
    --accent-1: #6366f1;
    --accent-2: #10b981;
    --accent-1-soft: rgba(99, 102, 241, 0.25);
    --accent-2-soft: rgba(16, 185, 129, 0.20);
    --surface-1: rgba(30, 41, 59, 0.65);
    --surface-2: rgba(20, 20, 50, 0.75);
    --radius-md: 14px;
    --radius-lg: 20px;
}

/* ── Trade Tab Background & Global ── */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(160deg, #0a0e17 0%, #111827 50%, #0f172a 100%);
}

/* ── Hero Header ── */
.hero-title {
    background: linear-gradient(90deg, #f1f5f9 15%, var(--accent-1) 65%, var(--accent-2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-size: 2.3rem; font-weight: 900; margin-bottom: 0.3rem; line-height: 1.2;
}
.hero-tagline { color: #94a3b8; font-size: 1rem; margin-bottom: 0.5rem; }

/* ── Consistent Tab Header (icon + gradient title, every tab) ── */
.tab-header { text-align: center; margin-bottom: 0.2rem; }
.tab-header h2 {
    background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-size: 1.9rem; font-weight: 800; margin-bottom: 0;
}
.tab-header p { color: #94a3b8; font-size: 0.92rem; margin-top: 0.3rem; }

/* ── KPI Cards ── */
.kpi-card {
    background: linear-gradient(135deg, var(--surface-2), rgba(40,40,70,0.55));
    border: 1px solid var(--accent-1-soft);
    border-radius: var(--radius-md);
    padding: 1.1rem 1.2rem;
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
}
.kpi-label {
    color: #94a3b8; font-size: 0.78rem; text-transform: uppercase;
    letter-spacing: 0.06em; font-weight: 600;
}
.kpi-value { font-size: 1.9rem; font-weight: 800; color: #f1f5f9; margin: 0.2rem 0; }
.kpi-delta-up { color: var(--accent-2); font-size: 0.82rem; font-weight: 700; }
.kpi-delta-down { color: #ef4444; font-size: 0.82rem; font-weight: 700; }

/* ── Sidebar Expander Grouping ── */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid rgba(99,102,241,0.18);
    border-radius: var(--radius-md);
    margin-bottom: 0.7rem;
    background: rgba(20,20,45,0.35);
}

/* ── Glassmorphism Cards ── */
.trade-card {
    background: rgba(30, 41, 59, 0.65);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.trade-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(99, 102, 241, 0.2);
}

/* ── Player Spotlight Card ── */
.player-spotlight {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(16, 185, 129, 0.10));
    backdrop-filter: blur(12px);
    border: 1px solid rgba(99, 102, 241, 0.35);
    border-radius: 20px;
    padding: 1.8rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.player-spotlight::before {
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%);
    animation: pulse-glow 4s ease-in-out infinite;
}
@keyframes pulse-glow {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.05); }
}

/* ── Interest Bar ── */
.interest-bar {
    background: rgba(30, 41, 59, 0.5);
    border-radius: 8px;
    overflow: hidden;
    height: 10px;
    margin: 4px 0 8px 0;
}
.interest-fill {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #6366f1, #10b981);
    transition: width 0.6s ease;
}

/* ── Trade Verdict Badges ── */
.verdict-accept {
    background: linear-gradient(135deg, #065f46, #10b981);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}
.verdict-lean {
    background: linear-gradient(135deg, #92400e, #f59e0b);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}
.verdict-decline {
    background: linear-gradient(135deg, #991b1b, #ef4444);
    color: white; font-weight: 800; font-size: 1.3rem;
    padding: 0.8rem 1.5rem; border-radius: 12px; text-align: center;
}

/* ── Section Dividers ── */
.section-glow {
    height: 2px;
    background: linear-gradient(90deg, transparent, #6366f1, #10b981, transparent);
    margin: 1.2rem 0;
    border: none;
}

/* ── Stat Pill ── */
.stat-pill {
    display: inline-block;
    background: rgba(99, 102, 241, 0.2);
    border: 1px solid rgba(99, 102, 241, 0.4);
    border-radius: 20px;
    padding: 4px 14px;
    margin: 3px;
    font-size: 0.85rem;
    color: #c7d2fe;
}

/* ── Global Premium Enhancements ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d0d22 0%, #1a1a3e 100%);
    border-right: 1px solid rgba(99, 102, 241, 0.2);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 8px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background: rgba(20, 20, 50, 0.6);
    border-radius: 10px 10px 0 0;
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-bottom: none;
    padding: 0.6rem 1.2rem;
    transition: background 0.2s;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: rgba(99, 102, 241, 0.2) !important;
    border-color: rgba(99, 102, 241, 0.4) !important;
}
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(20,20,50,0.8), rgba(40,40,70,0.6));
    border: 1px solid rgba(99, 102, 241, 0.15);
    border-radius: 12px;
    padding: 1rem;
}
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

/* ── Depth Chart Cards ── */
.dc-card {
    background: linear-gradient(135deg, rgba(25,25,55,0.9), rgba(45,45,75,0.7));
    border-radius: 12px;
    padding: 0.7rem;
    text-align: center;
    border: 1px solid rgba(99,102,241,0.2);
    margin-bottom: 0.5rem;
    transition: transform 0.2s, box-shadow 0.2s;
}
.dc-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(99,102,241,0.15);
}
.dc-starter { border-left: 3px solid #00e676; }
.dc-backup  { border-left: 3px solid #ffc107; opacity: 0.85; }
</style>"""


def inject_css() -> None:
    """Install the dashboard stylesheet. Call once, before anything renders."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_hero() -> None:
    """Top-of-page franchise title and tagline."""
    st.markdown(
        '<div class="hero-title">🏈 Madden NFL 27: Franchise Strategy Audit</div>',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-tagline">UI optimized for <b>Madden 27</b> franchise '
        'workflows — upgraded <b>Coach DNA</b> and <b>Wear &amp; Tear</b> insights.</div>',
        unsafe_allow_html=True)


def render_tab_header(icon: str, title: str, subtitle: str = "") -> None:
    """Gradient icon-title header + divider, used at the top of every tab."""
    subtitle_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"""
    <div class="tab-header">
        <h2>{icon} {title}</h2>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)
    divider()


def divider() -> None:
    """The glowing gradient rule used between major sections."""
    st.markdown('<div class="section-glow"></div>', unsafe_allow_html=True)


def kpi_card_html(label: str, value: str, delta: str = "",
                  delta_positive: bool = True) -> str:
    """Markup for one KPI tile. Returns HTML; the caller renders it."""
    delta_html = ""
    if delta:
        cls = "kpi-delta-up" if delta_positive else "kpi-delta-down"
        arrow = "▲" if delta_positive else "▼"
        delta_html = f'<div class="{cls}">{arrow} {delta}</div>'
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """
