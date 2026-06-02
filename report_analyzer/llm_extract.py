"""Free / bring-your-own LLM extraction backend (OpenAI-compatible API).

Works with any OpenAI-compatible endpoint so you can run extraction for free:

* **Google Gemini** free tier - key at https://aistudio.google.com/apikey (default)
* **Groq** free tier
* **OpenRouter** (has free models)
* a local **Ollama** server (fully offline, no key)

It reuses the same instruction prompt, field schema, and ``Report`` mapping as
the Claude backend (``ai_extract``), so the output is identical regardless of
which model produced it. Importing from ``ai_extract`` here does **not** pull in
the ``anthropic`` package (that SDK is imported lazily, only inside the Claude
call path).
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .ai_extract import SCHEMA, SYSTEM_PROMPT, _to_report
from .extraction import load_document
from .models import Report

# Sensible defaults per provider. base_url is the OpenAI-compatible endpoint.
PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.0-flash",
        "key_env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "help": "Get a free key at https://aistudio.google.com/apikey, then set GEMINI_API_KEY.",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_env": ["GROQ_API_KEY"],
        "help": "Get a free key at https://console.groq.com/keys, then set GROQ_API_KEY.",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "key_env": ["OPENROUTER_API_KEY"],
        "help": "Get a key at https://openrouter.ai/keys, then set OPENROUTER_API_KEY.",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "key_env": ["OLLAMA_API_KEY"],
        "help": "Run a local model with Ollama (https://ollama.com); no key needed.",
    },
}

DEFAULT_PROVIDER = "gemini"


def provider_key_envs() -> list:
    """Env var names that, if set, indicate a usable free-LLM provider."""
    names = []
    for cfg in PROVIDERS.values():
        names.extend(cfg["key_env"])
    return names


def _resolve(provider: str, base_url: Optional[str], model: Optional[str], api_key: Optional[str]):
    cfg = PROVIDERS.get(provider, {})
    base_url = base_url or os.environ.get("LLM_BASE_URL") or cfg.get("base_url")
    model = model or os.environ.get("LLM_MODEL") or cfg.get("model")
    if not api_key:
        for env in cfg.get("key_env", []):
            if os.environ.get(env):
                api_key = os.environ[env]
                break
        api_key = api_key or os.environ.get("LLM_API_KEY")
    if provider == "ollama" and not api_key:
        api_key = "ollama"  # Ollama ignores the key but the SDK requires a non-empty one
    return base_url, model, api_key


def _skeleton(schema: dict):
    """Build an empty example matching the schema, to show the model the shape."""
    t = schema.get("type")
    if t == "object":
        return {k: _skeleton(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [_skeleton(schema["items"])]
    return ""


def _parse_json(content: str) -> dict:
    """Parse a JSON object out of a model reply (tolerating ``` fences / prose)."""
    s = (content or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start:end + 1])
        raise RuntimeError("The model did not return valid JSON. Try a different --provider/--llm-model.")


def _build_client(base_url: str, api_key: str):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Free-LLM mode needs the 'openai' package: pip install openai") from exc
    return OpenAI(base_url=base_url, api_key=api_key)


def analyze_text_llm(
    text: str,
    source: str = "",
    provider: str = DEFAULT_PROVIDER,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    client=None,
) -> Report:
    """Extract a :class:`Report` from report text via an OpenAI-compatible LLM."""
    base_url, model, api_key = _resolve(provider, base_url, model, api_key)
    if client is None:
        if not api_key:
            cfg = PROVIDERS.get(provider, {})
            raise RuntimeError(
                f"No API key found for provider '{provider}'. {cfg.get('help', '')} "
                "Or choose another with --provider (gemini/groq/openrouter/ollama)."
            )
        if not base_url or not model:
            raise RuntimeError(
                "Set --provider, or pass --llm-base-url and --llm-model for a custom endpoint."
            )
        client = _build_client(base_url, api_key)

    prompt = (
        SYSTEM_PROMPT
        + "\n\nReturn ONLY a single JSON object with exactly this shape "
        "(no markdown, no commentary). Use \"\" for unknown fields and [] for "
        "empty lists:\n"
        + json.dumps(_skeleton(SCHEMA), indent=2)
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Test report text:\n\n{text}"},
    ]
    # Prefer JSON mode; fall back if the provider/model rejects response_format.
    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0)

    content = resp.choices[0].message.content
    return _to_report(_parse_json(content), source)


def analyze_pdf_llm(
    path: str,
    provider: str = DEFAULT_PROVIDER,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    password: str = "",
    client=None,
) -> Report:
    """Load a PDF and extract it via an OpenAI-compatible (free) LLM."""
    doc = load_document(path, password=password)
    report = analyze_text_llm(
        doc.full_text, source=path, provider=provider, model=model,
        base_url=base_url, api_key=api_key, client=client,
    )
    report.source_file = path
    return report
