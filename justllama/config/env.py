"""Load/persist secret API keys from a project-root .env file via python-dotenv."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"  # <project root>/.env
# Pre-existing installs stored keys inside the package; keep reading them.
_LEGACY_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"  # justllama/.env
_PROVIDER_ENV = {
    "nvidia": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "opencode": "OPENCODE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "kilocode": "KILOCODE_API_KEY",
}


def load_env() -> None:
    """Load .env into os.environ. No-op (and no error) if the file is absent.

    The project-root .env is canonical; the legacy in-package location is
    still read (without overriding) so older installs keep working.
    """
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
    load_dotenv(dotenv_path=_LEGACY_ENV_PATH, override=False)


def get_api_key(provider: str) -> str:
    """Return the key for a cloud provider from os.environ (populated by load_env)."""
    if provider not in _PROVIDER_ENV:
        raise ValueError(f"Unknown API provider: {provider!r}")
    return os.environ.get(_PROVIDER_ENV[provider], "")


def set_api_key(provider: str, value: str) -> None:
    """Persist a key to the project-root .env and make it visible in the
    current process."""
    if provider not in _PROVIDER_ENV:
        raise ValueError(f"Unknown API provider: {provider!r}")
    var = _PROVIDER_ENV[provider]
    set_key(dotenv_path=_ENV_PATH, key_to_set=var, value_to_set=value)
    os.environ[var] = value
