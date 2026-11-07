"""Formatting helpers, shared chart styling and small UI components."""
from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

CURRENCY = os.getenv("CURRENCY_SYMBOL", "R$")

# One restrained palette used everywhere; sequential scale for magnitude, two hues for good/bad.
PRIMARY = "#1b7f5c"
ACCENT = "#d97706"
BAD = "#c0392b"
NEUTRAL = "#8a9a94"
SEQUENCE = ["#1b7f5c", "#3fa37c", "#7cc4a4", "#b9e0cc", "#d97706", "#e9a64b", "#8a9a94"]


def money(x: float | None, compact: bool = False) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    if compact:
        for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
            if abs(x) >= div:
                return f"{CURRENCY} {x / div:,.2f}{unit}"
    return f"{CURRENCY} {x:,.2f}"


def number(x: float | None) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:,.0f}"


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10),
                      template="plotly_white", title_font_size=16,
                      legend=dict(orientation="h", y=-0.2))
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch")


def table(df: pd.DataFrame, **kwargs) -> None:
    st.dataframe(df, width="stretch", hide_index=True, **kwargs)


def empty_notice(df: pd.DataFrame, what: str = "this view") -> bool:
    """Show a friendly message and return True when a query returned nothing."""
    if df is None or df.empty:
        st.info(f"No data for {what} with the current filters. Try widening the date range or "
                "choosing 'All' states/categories.")
        return True
    return False


def line_chart(df, x, y, title, ylabel=None):
    fig = px.line(df, x=x, y=y, markers=True, title=title, color_discrete_sequence=[PRIMARY])
    fig.update_yaxes(title=ylabel or y)
    return style(fig)


def bar_chart(df, x, y, title, horizontal=False, color=None, text=None, height=380):
    if horizontal:
        fig = px.bar(df, x=y, y=x, orientation="h", title=title, text=text, color=color,
                     color_discrete_sequence=[PRIMARY] if color is None else SEQUENCE)
        fig.update_yaxes(autorange="reversed")
    else:
        fig = px.bar(df, x=x, y=y, title=title, text=text, color=color,
                     color_discrete_sequence=[PRIMARY] if color is None else SEQUENCE)
    return style(fig, height)


def insight_card(ins: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{ins['area']}**")
        st.markdown(f"**Observation:** {ins['observation']}")
        st.markdown(f"**Interpretation:** {ins['interpretation']}")
        st.markdown(f"**Business impact:** {ins['business_impact']}")
        st.markdown(f"**Recommendation:** {ins['recommendation']}")


def p_value_text(p: float) -> str:
    return "< 0.0001" if p < 0.0001 else f"{p:.4f}"
