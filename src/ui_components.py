"""
Reusable UI component library for MaddenGM Dashboard.
Provides helper functions that emit styled HTML/Markdown via Streamlit.
"""

import streamlit as st


# ── Colour palette ────────────────────────────────────────────────────────────
COLORS = {
    "primary": "#6366f1",
    "success": "#10b981",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "info": "#3b82f6",
    "muted": "#94a3b8",
    "surface": "rgba(30, 41, 59, 0.65)",
    "surface_hover": "rgba(45, 55, 72, 0.80)",
    "border": "rgba(99, 102, 241, 0.25)",
    "text": "#f1f5f9",
    "text_muted": "#94a3b8",
}


# ── Card components ────────────────────────────────────────────────────────────

def card(content_html: str, accent: str = COLORS["primary"],
         extra_style: str = "") -> None:
    """Render a glassmorphism-style card with an accent left border.

    Args:
        content_html: Raw HTML string to render inside the card.
        accent: CSS colour value used for the left border and shadow tint.
        extra_style: Additional inline CSS appended to the card container.
    """
    st.markdown(
        f"""
        <div style="
            background: {COLORS['surface']};
            backdrop-filter: blur(12px);
            border: 1px solid {accent}40;
            border-left: 4px solid {accent};
            border-radius: 12px;
            padding: 1rem 1.2rem;
            margin-bottom: 0.8rem;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            {extra_style}
        ">
            {content_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def stat_card(label: str, value: str, delta: str = "",
              accent: str = COLORS["primary"]) -> None:
    """Render a compact stat card with label, value, and optional delta.

    Args:
        label: Short description shown above the value (e.g. "Win Rate").
        value: Primary metric value to display (e.g. "87.5%").
        delta: Optional change indicator string.  Strings starting with '-'
            are coloured red (decline); all others are coloured green (gain).
            Example: "+3.2" or "-1.5".
        accent: CSS colour value for the card's top accent border.
    """
    delta_html = ""
    if delta:
        positive = not delta.startswith("-")
        delta_color = COLORS["success"] if positive else COLORS["danger"]
        arrow = "▲" if positive else "▼"
        delta_html = (
            f'<div style="color:{delta_color}; font-size:0.8rem; '
            f'font-weight:700; margin-top:2px;">{arrow} {delta}</div>'
        )
    st.markdown(
        f"""
        <div style="
            background: {COLORS['surface']};
            border: 1px solid {accent}40;
            border-top: 3px solid {accent};
            border-radius: 10px;
            padding: 0.9rem 1rem;
            text-align: center;
            margin-bottom: 0.5rem;
        ">
            <div style="color:{COLORS['text_muted']}; font-size:0.78rem;
                text-transform:uppercase; letter-spacing:0.05em;">
                {label}
            </div>
            <div style="color:{COLORS['text']}; font-size:1.5rem;
                font-weight:800; margin-top:4px;">
                {value}
            </div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Badge / pill helpers ───────────────────────────────────────────────────────

def badge(text: str, color: str = COLORS["primary"]) -> str:
    """Return an inline HTML badge string (use inside f-strings).

    Args:
        text: Label text to display inside the badge.
        color: CSS colour value for the badge border and text tint.
    """
    return (
        f'<span style="background:{color}22; color:{color}; '
        f'border:1px solid {color}55; border-radius:6px; '
        f'padding:2px 8px; font-size:0.75rem; font-weight:700; '
        f'letter-spacing:0.03em;">{text}</span>'
    )


def pill(text: str, color: str = COLORS["primary"]) -> str:
    """Return an inline HTML pill string (fully rounded).

    Args:
        text: Label text to display inside the pill.
        color: CSS colour value for the pill border and text tint.
    """
    return (
        f'<span style="background:{color}22; color:{color}; '
        f'border:1px solid {color}55; border-radius:999px; '
        f'padding:2px 10px; font-size:0.75rem; font-weight:700;">'
        f'{text}</span>'
    )


# ── Progress bar ───────────────────────────────────────────────────────────────

def progress_bar(value: float, max_value: float = 100.0,
                 color: str = COLORS["primary"],
                 height: int = 8, label: str = "") -> None:
    """Render a custom styled progress bar (value 0–max_value).

    Args:
        value: Current progress value.
        max_value: Maximum value (determines 100 % fill).  Defaults to 100.
        color: CSS colour value used as the right-side gradient stop.
        height: Bar height in pixels.
        label: Optional text displayed above the bar.
    """
    pct = min(max(value / max_value * 100, 0), 100)
    label_html = (
        f'<div style="color:{COLORS["text_muted"]}; font-size:0.78rem; '
        f'margin-bottom:4px;">{label}</div>'
        if label else ""
    )
    st.markdown(
        f"""
        {label_html}
        <div style="background:rgba(30,41,59,0.5); border-radius:{height}px;
            overflow:hidden; height:{height}px; margin-bottom:0.4rem;">
            <div style="width:{pct:.1f}%; height:100%; border-radius:{height}px;
                background:linear-gradient(90deg, {COLORS['primary']}, {color});
                transition:width 0.6s ease;">
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Section divider ────────────────────────────────────────────────────────────

def section_divider() -> None:
    """Render a glowing gradient section divider."""
    st.markdown(
        """
        <hr style="height:2px; border:none;
            background:linear-gradient(90deg, transparent,
            #6366f1, #10b981, transparent);
            margin:1.2rem 0;" />
        """,
        unsafe_allow_html=True,
    )


# ── Status indicator ───────────────────────────────────────────────────────────

def status_indicator(state: str, message: str) -> None:
    """Show a colored status banner.

    Args:
        state: One of ``'success'``, ``'warning'``, ``'error'``, or
            ``'info'``.  Controls the accent color and leading icon.
        message: Text to display inside the banner.
    """
    _map = {
        "success": (COLORS["success"], "✅"),
        "warning": (COLORS["warning"], "⚠️"),
        "error": (COLORS["danger"], "❌"),
        "info": (COLORS["info"], "ℹ️"),
    }
    color, icon = _map.get(state, (COLORS["info"], "ℹ️"))
    st.markdown(
        f"""
        <div style="background:{color}18; border:1px solid {color}44;
            border-left:4px solid {color}; border-radius:8px;
            padding:0.5rem 0.8rem; margin-bottom:0.5rem;
            color:{COLORS['text']}; font-size:0.9rem;">
            {icon} {message}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Data table styling ─────────────────────────────────────────────────────────

def styled_dataframe(df, height: int = 400) -> None:
    """Display a dataframe with consistent dark-theme styling.

    Args:
        df: A ``pandas.DataFrame`` to render.
        height: Table height in pixels.
    """
    st.dataframe(
        df,
        use_container_width=True,
        height=height,
    )
