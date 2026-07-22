"""
Persisted configuration for knowpiler.

Design call: Level-0 (normalize.sh) picked an LLM backend by silently checking env vars in a fixed priority order. Step 4 of the Level-2 pipeline -- the semantic rewrite that resolves contradictions and marks [UNKNOWN] -- is the single most consequential LLM call in the whole system. Which model produced that rewrite is itself part of the traceability record. So: the backend is a config value, set explicitly via `knowpiler config set-backend`, recorded into each project's manifest when `rewrite` runs. Env vars still hold the actual credentials which are stored securely in a local .env file (never in config.toml).
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional

import dotenv
import tomli_w
from pydantic import BaseModel

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore

KNOWPILER_HOME = Path(os.environ.get("KNOWPILER_HOME", Path.home() / ".knowpiler"))
CONFIG_PATH = KNOWPILER_HOME / "config.toml"
ENV_PATH = KNOWPILER_HOME / ".env"

# Project data (staging output, eventually the Layer 1+2 knowledge corpus)
# lives in a *visible* folder, deliberately separate from KNOWPILER_HOME.
# KNOWPILER_HOME starts with a dot -- hidden by default in Finder/Explorer,
# which is fine for config.toml/.env (credential-adjacent, shouldn't be
# casually browsed) but actively hostile for evidence a non-technical user
# needs to find later. Confirmed as a real problem via live `init` testing
# in Level 2.2, not a theoretical one.
KNOWPILER_PROJECTS_HOME = Path(os.environ.get("KNOWPILER_PROJECTS_HOME", Path.home() / "knowpiler-projects"))

SUPPORTED_BACKENDS = ("claude", "gemini", "openai", "deepseek", "kimi", "ollama")

ENV_VAR_BY_BACKEND = {
    "claude": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "ollama": "OLLAMA_BASE_URL",
}

# Auto-hydrate process memory with the secure .env file if it exists
def hydrate_env() -> None:
    """Explicitly loads environment variables. Call once at CLI startup."""
    if ENV_PATH.exists():
        dotenv.load_dotenv(ENV_PATH)

class Config(BaseModel):
    backend: Optional[str] = None
    model: Optional[str] = None
    storage_root: str = str(KNOWPILER_PROJECTS_HOME)
    # Unified Layer 1 + Layer 2 corpus -- this is what Level 3/4 will read from.
    knowledge_root: str = str(KNOWPILER_PROJECTS_HOME / "_knowledge")


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)


def save_config(cfg: Config) -> None:
    KNOWPILER_HOME.mkdir(parents=True, exist_ok=True)
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

def save_credential(env_var: str, value: str) -> None:
    """Securely saves any credential to ~/.knowpiler/.env and updates current session."""
    KNOWPILER_HOME.mkdir(parents=True, exist_ok=True)
    
    # Save the key to the .env file
    dotenv.set_key(ENV_PATH, env_var, value)
    
    # Lock down file permissions: Read/Write for owner ONLY on POSIX systems
    if os.name != "nt":
        ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    
    # Instantly inject it into the running process memory
    os.environ[env_var] = value

def get_vault_status() -> dict:
    """
    Reads the .env file directly from disk. 
    Safe for tests and dry-runs because it never mutates os.environ.
    """
    if not ENV_PATH.exists():
        return {}
    return dotenv.dotenv_values(ENV_PATH)

def unset_credential(env_var: str) -> None:
    """Removes a credential from the .env vault and current session."""
    if ENV_PATH.exists():
        dotenv.unset_key(ENV_PATH, env_var)
    if env_var in os.environ:
        del os.environ[env_var]