"""
Academic Document Generator — Main Streamlit Application
Single entry point with sidebar navigation.
"""

import streamlit as st
from pathlib import Path

# App configuration
APP_DIR = Path(__file__).parent.resolve()
st.set_page_config(
    page_title="Generator Academic",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Navigation
PAGES = {
    "Generator": "generator",
    "Editor": "editor",
    "Registru": "registry",
    "Diagnostic API": "diagnostics",
}

st.sidebar.title("Generator Academic")
st.sidebar.markdown("---")
page = st.sidebar.radio("Navigare", list(PAGES.keys()), label_visibility="collapsed")

# Route to selected page
if page == "Generator":
    from pages.generator import render
    render(APP_DIR)
elif page == "Editor":
    from pages.editor import render
    render(APP_DIR)
elif page == "Registru":
    from pages.registry_page import render
    render(APP_DIR)
elif page == "Diagnostic API":
    from pages.diagnostics import render
    render(APP_DIR)
