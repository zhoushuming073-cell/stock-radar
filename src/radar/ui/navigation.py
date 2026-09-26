"""Sidebar navigation for the Strategy Lab Streamlit UI."""

from __future__ import annotations

import streamlit as st

DEFAULT_PAGE = "Lab"
TOP_PAGES = ("Lab", "Strategies", "Experiments", "Compare")
BOTTOM_PAGES = ("Data", "Settings")
PAGES = TOP_PAGES + BOTTOM_PAGES
ICONS = {
    "Lab": ":material/monitoring:",
    "Strategies": ":material/account_tree:",
    "Experiments": ":material/science:",
    "Compare": ":material/compare_arrows:",
    "Data": ":material/database:",
    "Settings": ":material/settings:",
}

_STATE_KEY = "radar_lab_page"


def _nav_button(label: str) -> None:
    active = st.session_state[_STATE_KEY] == label
    if st.sidebar.button(
        label,
        key=f"nav_{label}",
        type="primary" if active else "secondary",
        width="stretch",
        icon=ICONS[label],
    ):
        st.session_state[_STATE_KEY] = label
        st.rerun()


def render() -> str:
    """Render the sidebar nav and return the active page key (defaults to Lab).

    Layout matches the prototype: Lab, Strategies, Experiments, Compare,
    then a separator, then Data and Settings. There is no Dashboard item and
    no top-level Runs item.
    """
    st.session_state.setdefault(_STATE_KEY, DEFAULT_PAGE)

    st.sidebar.markdown("### ▥ Stock Radar")

    for label in TOP_PAGES:
        _nav_button(label)
    st.sidebar.divider()
    for label in BOTTOM_PAGES:
        _nav_button(label)

    return st.session_state[_STATE_KEY]
