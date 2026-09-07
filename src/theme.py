"""
The dashboard's two colour scales, in one place.

Before this module, green/amber/red encoded six unrelated things at once —
OVR tier, letter grade, KEEP/TRADE/CUT verdict, positional need level,
trade value, and roster tier — each with its own hardcoded hex map in a
different file. Within a single scroll of Roster Explorer, green meant
both "elite rating" and "take no action".

Two scales now, chosen so they cannot be confused:

    STATUS_*  semantic  — action required. Verdicts and need levels only.
    RANK      sequential — quality, low to high. Ratings, grades, values.

The sequential scale is deliberately blue-violet rather than red/amber/
green, so a low rating never reads as "act now" and a high one never reads
as "leave it alone".

`app.py` mirrors these as CSS custom properties for markup that can't call
Python. Keep the two in sync — this module is the source of truth.

Every value clears WCAG AA (4.5:1) against #0f172a, the darkest stop of the
page background gradient; measured ratios are noted inline.
"""

# ── Semantic: action required ──
STATUS_GOOD = "#10b981"   # 7.04:1 — no action needed
STATUS_WARN = "#f59e0b"   # 8.31:1 — worth a look
STATUS_BAD = "#ef4444"    # 4.74:1 — act now

VERDICT_COLORS = {
    "KEEP": STATUS_GOOD,
    "TRADE": STATUS_WARN,
    "CUT": STATUS_BAD,
}

NEED_COLORS = {
    "Set": STATUS_GOOD,
    "Moderate": STATUS_WARN,
    "Critical": STATUS_BAD,
}

# ── Sequential: quality, low to high ──
RANK_COLORS = [
    "#94a3b8",   # 6.96:1  lowest
    "#7dd3fc",   # 10.71:1
    "#a5b4fc",   # 8.96:1
    "#c4b5fd",   # 9.67:1  highest
]

# ── Text ──
# #666 (3.11:1) and #64748b (3.75:1) both failed AA and are no longer used.
TEXT_BRIGHT = "#f1f5f9"   # 16.30:1
TEXT_DIM = "#cbd5e1"      # 12.02:1
TEXT_MUTED = "#94a3b8"    # 6.96:1 — lowest permitted for body text


def rank_color(value: float, thresholds: "list[float]") -> str:
    """Pick a RANK_COLORS entry by ascending thresholds.

    `thresholds` must hold len(RANK_COLORS) - 1 ascending edges; a value
    below the first edge gets the lowest colour, at or above the last edge
    the highest.
    """
    for i, edge in enumerate(thresholds):
        if value < edge:
            return RANK_COLORS[i]
    return RANK_COLORS[-1]
