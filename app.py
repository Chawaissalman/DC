"""
AI Data Center Cooling – Thermodynamic & Techno-Economic Model
=============================================================
A parametric screening, digital-twin, techno-economic comparison,
and business-case optimizer for advanced cooling architectures.

Uses CoolProp for refrigerant / fluid property calculations.
"""

import streamlit as st

st.set_page_config(
    page_title="DC Cooling Model",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,500;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
    --bg-dark: #0e1117;
    --card-bg: #161b22;
    --accent: #58a6ff;
    --accent2: #3fb950;
    --warn: #d29922;
    --danger: #f85149;
    --text: #c9d1d9;
    --muted: #8b949e;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
code, .stCode, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: var(--card-bg);
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 14px 18px;
}
div[data-testid="stMetric"] label {
    color: var(--muted) !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-weight: 700;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #21262d;
}
section[data-testid="stSidebar"] .stRadio > label {
    font-weight: 500;
}

/* Tab styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px;
    border-bottom: 2px solid #21262d;
}
.stTabs [data-baseweb="tab"] {
    padding: 10px 24px;
    font-weight: 500;
    letter-spacing: 0.01em;
}

h1, h2, h3 {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar Navigation ──────────────────────────────────────
st.sidebar.markdown("## ❄️ DC Cooling Model")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "🔎 A – Parametric Screening",
        "🔬 B – Thermodynamic Twin",
        "💰 C – Techno-Economic Compare",
        "🏢 D – Business-Case Optimizer",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "CoolProp-backed thermodynamic model · "
    "Data from Vertiv / NVIDIA / Introl / Siemens Energy analyses"
)

# ── Page Router ─────────────────────────────────────────────
if page.startswith("🔎"):
    from pages import parametric_screening
    parametric_screening.render()
elif page.startswith("🔬"):
    from pages import thermo_twin
    thermo_twin.render()
elif page.startswith("💰"):
    from pages import techno_economic
    techno_economic.render()
elif page.startswith("🏢"):
    from pages import business_case
    business_case.render()
