"""Raw Data tab — the unmodified game log table."""

import streamlit as st

from views import theme
from views.context import AppContext


def render(ctx: AppContext) -> None:
    theme.render_tab_header("🗂️", "Raw Data", "Full historical game log table")
    st.dataframe(ctx.df)
