"""
AI provider management with automatic fallback between OpenAI, Anthropic, and Gemini.
"""

import os
import re
import time
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Meta-text patterns to strip from AI output (Romanian)
META_PATTERNS = [
    r'^(?:Iată|În continuare|Voi prezenta|Am pregătit|Mai jos|Desigur|Bineînțeles|Sigur|Cu plăcere)[^.]*[.:]\s*',
    r'^(?:Here is|Below is|I will present|I have prepared|Let me|Sure|Of course|Certainly)[^.]*[.:]\s*',
    r'^\*\*[^*]+\*\*\s*\n',  # Bold headers at start
]


class AIProviderError(Exception):
    """Raised when an AI provider call fails."""
    pass


class AIProvider:
    """Base class for AI providers."""

    def __init__(self, name: str, api_key: str, model: str):
        self.name = name
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096, temperature: float = 0.7) -> str:
        raise NotImplementedError


class ClaudeProvider(AIProvider):
    def __init__(self):
        key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        super().__init__("Claude", key, model)

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096, temperature: float = 0.7) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        response = client.messages.create(**kwargs)
        return response.content[0].text


class OpenAIProvider(AIProvider):
    def __init__(self):
        key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        super().__init__("OpenAI", key, model)

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096, temperature: float = 0.7) -> str:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content


class GeminiProvider(AIProvider):
    def __init__(self):
        key = os.getenv("GEMINI_API_KEY", "")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        super().__init__("Gemini", key, model)

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096, temperature: float = 0.7) -> str:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        # Disable all safety filters for academic content generation
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        response = model.generate_content(
            full_prompt,
            generation_config=genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
            safety_settings=safety_settings,
        )

        # Check for blocked content
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            # finish_reason: STOP=1, MAX_TOKENS=2, SAFETY=3, RECITATION=4
            fr = getattr(candidate, 'finish_reason', None)
            if fr is not None and fr not in (1, 2):  # Allow STOP and MAX_TOKENS
                # Try to get text anyway before raising
                try:
                    return response.text
                except Exception:
                    raise Exception(
                        f"Gemini a blocat conținutul (finish_reason={fr}). "
                        "Încercați alt provider sau reformulați cererea."
                    )
        elif not getattr(response, 'candidates', None):
            raise Exception(
                "Gemini nu a returnat niciun rezultat. "
                "Încercați alt provider sau reformulați cererea."
            )

        try:
            return response.text
        except ValueError as e:
            raise Exception(f"Gemini a blocat conținutul: {e}. Încercați alt provider.")


# Provider registry
PROVIDER_CLASSES = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    # "gemini": GeminiProvider,  # Disabled — content safety blocks academic content
}

# Gemini class kept in code for future re-enablement
_ALL_PROVIDER_CLASSES = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_available_providers() -> dict[str, AIProvider]:
    """Return dict of providers that have API keys configured."""
    available = {}
    key_map = {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        # "gemini": "GEMINI_API_KEY",  # Disabled
    }
    for name, env_key in key_map.items():
        if os.getenv(env_key, "").strip():
            available[name] = PROVIDER_CLASSES[name]()
    return available


def clean_meta_text(text: str) -> str:
    """Remove AI meta-text artifacts from generated content."""
    cleaned = text.strip()
    for pattern in META_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.MULTILINE | re.IGNORECASE)
    return cleaned.lstrip('\n').strip()


def generate_text(
    prompt: str,
    system_prompt: str = "",
    provider_order: list[str] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    max_retries: int = 2,
) -> tuple[str, str]:
    """Generate text using AI providers with automatic fallback.

    Args:
        prompt: The user/content prompt
        system_prompt: System instructions for the AI
        provider_order: Preferred order of providers (e.g. ["claude", "openai", "gemini"])
        max_tokens: Maximum tokens in response
        temperature: Sampling temperature
        max_retries: Retries per provider before fallback

    Returns:
        Tuple of (generated_text, provider_name_used)

    Raises:
        AIProviderError if all providers fail.
    """
    available = get_available_providers()
    if not available:
        raise AIProviderError("Nu s-au găsit chei API valide. Configurați cel puțin o cheie API în fișierul .env")

    if provider_order is None:
        provider_order = ["claude", "openai", "gemini"]

    # Filter to only available providers, maintaining order
    ordered = [p for p in provider_order if p in available]
    # Add any available but not in order
    for p in available:
        if p not in ordered:
            ordered.append(p)

    errors = []
    for provider_name in ordered:
        provider = available[provider_name]
        for attempt in range(max_retries):
            try:
                logger.info(f"Trying {provider.name} (attempt {attempt + 1})...")
                text = provider.generate(prompt, system_prompt, max_tokens, temperature)
                if text and len(text.strip()) > 50:
                    cleaned = clean_meta_text(text)
                    return cleaned, provider.name
                else:
                    errors.append(f"{provider.name}: response too short ({len(text)} chars)")
                    break
            except Exception as e:
                error_msg = str(e)
                errors.append(f"{provider.name} attempt {attempt + 1}: {error_msg}")
                logger.warning(f"{provider.name} failed: {error_msg}")
                if "rate" in error_msg.lower() or "429" in error_msg:
                    # Rate limit: wait and retry instead of immediately giving up
                    wait_time = 15 * (attempt + 1)  # 15s, 30s
                    logger.info(f"Rate limited. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue  # Retry same provider after waiting
                time.sleep(1)

    raise AIProviderError(
        f"Toți providerii AI au eșuat.\n" + "\n".join(errors)
    )


def test_provider(provider_name: str) -> dict:
    """Test a specific AI provider connection."""
    key_map = {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    env_key = key_map.get(provider_name, "")
    api_key = os.getenv(env_key, "")

    result = {
        "provider": provider_name,
        "key_configured": bool(api_key.strip()),
        "key_masked": f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***",
        "model": "",
        "connected": False,
        "error": None,
    }

    if not api_key.strip():
        result["error"] = f"Cheia {env_key} nu este configurată în .env"
        return result

    if provider_name not in PROVIDER_CLASSES:
        result["error"] = f"Provider '{provider_name}' este dezactivat"
        return result

    try:
        provider = PROVIDER_CLASSES[provider_name]()
        result["model"] = provider.model
        text = provider.generate("Răspunde doar cu: OK", max_tokens=10, temperature=0)
        result["connected"] = bool(text)
    except Exception as e:
        result["error"] = str(e)

    return result
