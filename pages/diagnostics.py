"""
Diagnostics page — Test AI provider connections and configuration.
"""

import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

from core.ai_providers import test_provider, PROVIDER_CLASSES


def render(app_dir: Path):
    st.title("Diagnostic API")
    st.markdown("Verificați configurarea și conexiunea providerilor AI.")

    # Load .env
    env_path = app_dir / ".env"
    load_dotenv(env_path)

    # Provider info
    provider_info = {
        "claude": {
            "name": "Anthropic Claude",
            "env_key": "ANTHROPIC_API_KEY",
            "model_key": "ANTHROPIC_MODEL",
            "default_model": "claude-sonnet-4-20250514",
            "url": "https://console.anthropic.com/",
        },
        "openai": {
            "name": "OpenAI GPT",
            "env_key": "OPENAI_API_KEY",
            "model_key": "OPENAI_MODEL",
            "default_model": "gpt-4o-mini",
            "url": "https://platform.openai.com/api-keys",
        },
        "gemini": {
            "name": "Google Gemini",
            "env_key": "GEMINI_API_KEY",
            "model_key": "GEMINI_MODEL",
            "default_model": "gemini-1.5-pro",
            "url": "https://aistudio.google.com/app/apikey",
        },
    }

    # Display configuration status
    st.subheader("Configurare")
    for provider_name, info in provider_info.items():
        api_key = os.getenv(info["env_key"], "")
        model = os.getenv(info["model_key"], info["default_model"])

        col1, col2, col3 = st.columns([2, 3, 1])
        with col1:
            st.write(f"**{info['name']}**")
        with col2:
            if api_key:
                masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
                st.write(f"Cheie: `{masked}` | Model: `{model}`")
            else:
                st.write(f"Cheie: Nu este configurată")
        with col3:
            if api_key.strip():
                st.info("Cheie setată")
            else:
                st.error("Lipsă")

    st.markdown("---")

    # Connection test
    st.subheader("Test Conexiune")
    st.info("Apăsați butonul de mai jos pentru a testa conexiunea la fiecare provider configurat.")

    if st.button("Testează Toți Providerii", type="primary"):
        for provider_name, info in provider_info.items():
            with st.spinner(f"Se testează {info['name']}..."):
                result = test_provider(provider_name)

                if result["connected"]:
                    st.success(f"{info['name']}: Conectat | Model: {result['model']}")
                elif not result["key_configured"]:
                    st.warning(f"{info['name']}: Cheie API neconfigurată — adăugați {info['env_key']} în .env")
                else:
                    st.error(f"{info['name']}: Eroare — {result['error']}")

    # .env file helper
    st.markdown("---")
    st.subheader("Configurare .env")

    if env_path.exists():
        st.info(f"Fișierul `.env` există la: `{env_path}`")
    else:
        st.warning("Fișierul `.env` nu există. Copiați `.env.example` și completați cheile API.")

    with st.expander("Exemplu .env"):
        example_path = app_dir / ".env.example"
        if example_path.exists():
            st.code(example_path.read_text(), language="bash")
        else:
            st.code(
                "# AI Provider API Keys\n"
                "ANTHROPIC_API_KEY=sk-ant-xxxxx\n"
                "OPENAI_API_KEY=sk-proj-xxxxx\n"
                "GEMINI_API_KEY=xxxxx\n\n"
                "# Default models (optional)\n"
                "ANTHROPIC_MODEL=claude-sonnet-4-20250514\n"
                "OPENAI_MODEL=gpt-4o-mini\n"
                "GEMINI_MODEL=gemini-1.5-pro\n",
                language="bash",
            )
