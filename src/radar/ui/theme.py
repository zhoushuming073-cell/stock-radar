"""Compact light theme for the Strategy Lab Streamlit UI.

Mirrors the look of ``docs/phase3-strategy-lab-mockup.html``: a fixed 176px
light sidebar, a ``#f6f8fb`` canvas, white cards with thin borders, a blue
accent, and compact typography.
"""

from __future__ import annotations

import streamlit as st

SIDEBAR_WIDTH = "176px"

# Prototype color tokens (kept in one place so the CSS never drifts).
COLORS = {
    "bg": "#f6f8fb",
    "panel": "#ffffff",
    "line": "#e7ebf0",
    "text": "#172033",
    "muted": "#7a8499",
    "blue": "#2563eb",
    "blue_soft": "#eaf2ff",
    "green": "#13a66a",
    "red": "#e34b4b",
}

# Tokens use ``__name__`` placeholders and are substituted in ``apply_theme``
# so the literal CSS braces never clash with string formatting.
_CSS = """
<style>
:root {
  --sr-bg: __bg__;
  --sr-panel: __panel__;
  --sr-line: __line__;
  --sr-text: __text__;
  --sr-muted: __muted__;
  --sr-blue: __blue__;
  --sr-blue-soft: __blue_soft__;
}

.stApp {
  background: var(--sr-bg);
  color: var(--sr-text);
  font-family: Inter, system-ui, -apple-system, "Segoe UI", sans-serif;
}

/* Compact app frame: hide default chrome and tighten the main column. */
header[data-testid="stHeader"] { display: none; }
#MainMenu, footer { visibility: hidden; }
.block-container {
  max-width: 100%;
  padding-top: 0.45rem;
  padding-left: 1.25rem;
  padding-right: 1.25rem;
  padding-bottom: 2rem;
}

/* Fixed 176px light sidebar with a thin border. */
section[data-testid="stSidebar"] {
  width: __sidebar__ !important;
  min-width: __sidebar__ !important;
  max-width: __sidebar__ !important;
  background: #fbfcfe;
  border-right: 1px solid var(--sr-line);
}
section[data-testid="stSidebar"] > div {
  padding: 18px 12px;
}
section[data-testid="stSidebar"] h3 {
  font-size: 1rem !important;
  white-space: nowrap;
  margin: 0 0 1.2rem 0;
}

/* Sidebar nav buttons read as flat, left-aligned items. */
section[data-testid="stSidebar"] .stButton > button[kind="secondary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-secondary"] {
  background: transparent;
  border-color: transparent;
  color: #4b566b;
  text-align: left;
  justify-content: flex-start;
  border-radius: 9px;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
  background: var(--sr-blue-soft);
  border-color: transparent;
  color: var(--sr-blue);
  font-weight: 650;
  text-align: left;
  justify-content: flex-start;
  border-radius: 9px;
}

/* Compact typography. */
h1 { font-size: 1.5rem !important; letter-spacing: -0.02em; }
h2 { font-size: 1.2rem !important; }
h3 { font-size: 1.05rem !important; }
div[data-testid="stVerticalBlock"] { gap: 0.65rem; }

/* White cards with thin borders. */
div[data-testid="stMetric"],
div[data-testid="stPlotlyChart"],
div[data-testid="stDataFrame"],
div[data-testid="stExpander"],
div[data-testid="stForm"] {
  background: var(--sr-panel);
  border: 1px solid var(--sr-line);
  border-radius: 12px;
}
div[data-testid="stMetric"] { padding: 0.8rem 0.9rem; }
div[data-testid="stMetricLabel"] { color: var(--sr-muted); font-size: 0.75rem; }
div[data-testid="stMetricValue"] {
  color: var(--sr-text);
  font-size: 1.35rem;
  font-weight: 700;
}
div[data-testid="stPlotlyChart"],
div[data-testid="stDataFrame"] { padding: 0.4rem; }

/* Blue accent for primary actions, links, and active tabs. */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"],
.stButton > button[kind="primaryFormSubmit"] {
  background: var(--sr-blue);
  border-color: var(--sr-blue);
  color: #fff;
}
a { color: var(--sr-blue); }
div[data-testid="stTabs"] button[aria-selected="true"] {
  color: var(--sr-blue);
  border-color: var(--sr-blue);
}
div[data-testid="stButtonGroup"] [role="radiogroup"] {
  background: transparent !important;
  border: 0 !important;
  border-bottom: 1px solid var(--sr-line) !important;
  border-radius: 0 !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"] {
  background: transparent !important;
  border: 0 !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  color: #4b566b !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-checked="true"] {
  color: var(--sr-blue) !important;
  border-bottom-color: var(--sr-blue) !important;
  font-weight: 650;
}

/* Compact inputs and selects to match the prototype fields. */
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stSelectbox"] > div > div {
  border: 1px solid var(--sr-line);
  border-radius: 8px;
  background: var(--sr-panel);
}
input:disabled {
  color: var(--sr-text) !important;
  -webkit-text-fill-color: var(--sr-text) !important;
  opacity: 1 !important;
  background: var(--sr-panel) !important;
}

@media (max-width: 1100px) {
  .block-container {
    padding-top: 0.6rem;
    padding-left: 0.8rem;
    padding-right: 0.8rem;
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject the compact light theme into the current Streamlit app.

    Safe to call once from the app's ``main()``; no page config is touched so
    the host app keeps control of ``st.set_page_config``.
    """
    css = _CSS
    for name, value in COLORS.items():
        css = css.replace(f"__{name}__", value)
    css = css.replace("__sidebar__", SIDEBAR_WIDTH)
    st.markdown(css, unsafe_allow_html=True)
