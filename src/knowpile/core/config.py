"""
Persisted configuration for knowpile.

Design call: Level-0 (normalize.sh) picked an LLM backend by silently
checking env vars in a fixed priority order (Gemini > Kimi > Claude > OpenAI
> DeepSeek > Azure > Bedrock > Ollama > claude-cli). That's a reasonable
default for a low-stakes convenience call (graphify's own .graphifyignore
suggestion step), but Step 4 of the Level-2 pipeline -- the semantic rewrite
that resolves contradictions and marks [UNKNOWN] -- is the single most
consequential LLM call in the whole system. Which model produced that
rewrite is itself part of the traceability record.

So: the backend is a config value, set explicitly via `knowpile config
set-backend`, recorded into each project's manifest when `rewrite` runs.
Env vars still hold the actual credentials (never stored in config.toml),
and can still override the configured backend per-run for CI/headless use.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import tomli_w
from pydantic import BaseModel

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore

KNOWPILE_HOME = Path(os.environ.get("KNOWPILE_HOME", Path.home() / ".knowpile"))
CONFIG_PATH = KNOWPILE_HOME / "config.toml"

SUPPORTED_BACKENDS = ("claude", "gemini", "openai", "deepseek", "kimi", "ollama")

ENV_VAR_BY_BACKEND = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "ollama": "OLLAMA_BASE_URL",
}


class Config(BaseModel):
    backend: Optional[str] = None
    model: Optional[str] = None
    storage_root: str = str(KNOWPILE_HOME / "projects")
    # Unified Layer 1 + Layer 2 corpus -- this is what Level 3/4 will read from.
    knowledge_root: str = str(KNOWPILE_HOME / "knowledge")


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)


def save_config(cfg: Config) -> None:
    KNOWPILE_HOME.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "wb") as f:
        # TOML has no null type -- exclude unset Optional fields rather than
        # writing them as None, which tomli_w can't serialize at all.
        tomli_w.dump(cfg.model_dump(exclude_none=True), f)


def backend_ready(backend: str) -> bool:
    """Is the credential this backend needs actually present right now?"""
    env_var = ENV_VAR_BY_BACKEND.get(backend)
    if not env_var:
        return False
    if backend == "ollama":
        return True  # OLLAMA_BASE_URL defaults to localhost if unset
    return bool(os.environ.get(env_var))
