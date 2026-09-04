"""Wear & Tear tab — fatigue, turnovers, and rush/pass balance."""

import plotly.express as px
import streamlit as st

from views import theme
from views.context import AppContext


def render(ctx: AppContext) -> None:
    theme.render_tab_header(
        "💪", "Wear &amp; Tear",
        "How turnovers, defensive breakdowns, and fatigue impact your franchise")

    df = ctx.df

    if "Fatigue" in df.columns and "Points_For" in df.columns:
        fig_fatigue = px.bar(
            df.sort_values("Fatigue"),
            x="Fatigue",
            y="Points_For",
            color="Result" if "Result" in df.columns else None,
            title="Fatigue Level vs Offensive Production",
            template="plotly_dark",
        )
        st.plotly_chart(fig_fatigue, use_container_width=True)

    if "Turnovers" in df.columns and "Points_For" in df.columns:
        wt1, wt2 = st.columns(2)
        with wt1:
            fig_to = px.scatter(
                df, x="Turnovers", y="Points_For",
                color="Result" if "Result" in df.columns else None,
                color_discrete_map={"WIN": "#00e676", "LOSS": "#ff5252"},
                size="Total_Yards" if "Total_Yards" in df.columns else None,
                hover_data=["Opponent"],
                title="Turnovers vs Points Scored",
                template="plotly_dark",
            )
            st.plotly_chart(fig_to, use_container_width=True)
        with wt2:
            if "Total_Yards_Allowed" in df.columns and "Takeaways" in df.columns:
                fig_def = px.scatter(
                    df, x="Total_Yards_Allowed", y="Takeaways",
                    color="Result" if "Result" in df.columns else None,
                    color_discrete_map={"WIN": "#00e676", "LOSS": "#ff5252"},
                    hover_data=["Opponent"],
                    title="Yards Allowed vs Takeaways",
                    template="plotly_dark",
                )
                st.plotly_chart(fig_def, use_container_width=True)

    if "Pass_Yards" in df.columns and "Rush_Yards" in df.columns:
        balance_df = df[["Opponent", "Pass_Yards", "Rush_Yards", "Result"]].dropna()
        fig_bal = px.bar(
            balance_df, x="Opponent", y=["Pass_Yards", "Rush_Yards"],
            color_discrete_map={"Pass_Yards": "#6366f1", "Rush_Yards": "#10b981"},
            title="Pass vs Rush Yardage by Game",
            template="plotly_dark", barmode="stack",
        )
        fig_bal.update_layout(legend_title="Yard Type",
                              yaxis_title="Yards",
                              xaxis_title="Opponent")
        st.plotly_chart(fig_bal, use_container_width=True)
