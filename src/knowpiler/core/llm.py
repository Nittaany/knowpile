"""
Unified LLM gateway via `litellm` -- one call shape across every backend.

Maps knowpiler's own backend names (see core.config.SUPPORTED_BACKENDS) to
litellm's model-string convention. Credentials come from the same
per-provider env vars litellm already expects (ANTHROPIC_API_KEY,
GEMINI_API_KEY, etc.) -- no separate credential-plumbing code needed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import litellm

DEFAULT_MODEL_BY_BACKEND = {
    "claude": "claude-3-5-sonnet-20241022",
    "gemini": "gemini/gemini-2.0-flash",
    "openai": "gpt-4o",
    "deepseek": "deepseek/deepseek-chat",
    "kimi": "moonshot/moonshot-v1-8k",
    "ollama": "ollama/llama3",
}


@dataclass
class LLMResult:
    ok: bool
    text: Optional[str] = None
    error: Optional[str] = None


def complete(prompt: str, backend: str, model: Optional[str] = None) -> LLMResult:
    model_string = model or DEFAULT_MODEL_BY_BACKEND.get(backend)
    if not model_string:
        return LLMResult(ok=False, error=f"No model configured for backend '{backend}'")
    try:
        response = litellm.completion(
            model=model_string,
            messages=[{"role": "user", "content": prompt}],
            num_retries=3,
        )
        return LLMResult(ok=True, text=response.choices[0].message.content)
    except Exception as e:
        return LLMResult(ok=False, error=f"{type(e).__name__}: {e}")
