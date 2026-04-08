"""
Shared LLM client for scripts.

Reads configuration from environment variables so it's easy to swap between
Anthropic's API and a local Ollama instance without changing code.

.env settings:
    LLM_BASE_URL   API base URL
                   Anthropic: https://api.anthropic.com/v1
                   Ollama:    http://localhost:11434/v1
    LLM_API_KEY    API key ("ollama" works for local Ollama)
    LLM_MODEL      Model name, e.g. claude-haiku-4-5-20251001 or llama3.2

Uses the OpenAI-compatible SDK which works against both endpoints.
"""

import os
from pathlib import Path

from dotenv import dotenv_values
from openai import OpenAI

_dotenv = dotenv_values(Path(__file__).resolve().parent.parent.parent / ".env")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or _dotenv.get("LLM_BASE_URL", "https://api.anthropic.com/v1")
LLM_API_KEY  = os.environ.get("LLM_API_KEY") or _dotenv.get("LLM_API_KEY", "")
LLM_MODEL    = os.environ.get("LLM_MODEL")    or _dotenv.get("LLM_MODEL", "claude-haiku-4-5-20251001")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not LLM_API_KEY:
            raise EnvironmentError(
                "LLM_API_KEY is not set. Add it to your .env file.\n"
                "See .env.example for configuration options."
            )
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _client


def chat(messages: list[dict], *, model: str | None = None, **kwargs) -> str:
    """Simple chat completion, returns the text content of the first choice."""
    response = _get_client().chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def chat_json(messages: list[dict], *, model: str | None = None, **kwargs) -> dict | list:
    """
    Chat completion requesting JSON output.
    Passes response_format={"type": "json_object"} — supported by Anthropic and
    most Ollama models. Falls back to parsing the raw text if the provider
    doesn't support the parameter.
    """
    import json

    try:
        response = _get_client().chat.completions.create(
            model=model or LLM_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
        text = response.choices[0].message.content or "{}"
    except Exception:
        # Provider doesn't support response_format — ask in the prompt instead
        response = _get_client().chat.completions.create(
            model=model or LLM_MODEL,
            messages=messages,
            **kwargs,
        )
        text = response.choices[0].message.content or "{}"

    # Strip markdown code fences if the model wrapped the JSON
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    return json.loads(text)
