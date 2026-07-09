"""External API partner definitions for cloud model routing."""
from dataclasses import dataclass

from justllama.config.env import _PROVIDER_ENV  # provider -> env var map


@dataclass(frozen=True)
class Provider:
    id: str            # "nvidia" | "openrouter" | "opencode" | "gemini" | "kilocode"
    label: str         # Human label for UI, e.g. "NVIDIA"
    base_url: str      # OpenAI-compatible /v1 base; may be overridden at runtime
    env_var: str       # API key env var name (from _PROVIDER_ENV)
    api_prefix: str = "/v1"  # URL path prefix ("" for Gemini OpenAI compat, "/v1" default)

# Static base URLs (opencode's is overridable via cloud_endpoints/opencode at runtime).
_PROVIDERS = {
    "nvidia": Provider("nvidia", "NVIDIA", "https://integrate.api.nvidia.com", _PROVIDER_ENV["nvidia"]),
    "openrouter": Provider("openrouter", "OpenRouter", "https://openrouter.ai/api", _PROVIDER_ENV["openrouter"]),
    "opencode": Provider("opencode", "Opencode", "https://api.opencode.com", _PROVIDER_ENV["opencode"]),
    "gemini": Provider("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", _PROVIDER_ENV["gemini"], api_prefix=""),
    "kilocode": Provider("kilocode", "Kilocode", "https://api.kilocode.com", _PROVIDER_ENV["kilocode"]),
}
PROVIDER_IDS = tuple(_PROVIDERS.keys())


def get_provider(provider_id: str) -> Provider:
    if provider_id not in _PROVIDERS:
        raise ValueError(f"Unknown API provider: {provider_id!r}")
    return _PROVIDERS[provider_id]

def provider_base_url(provider_id: str, settings) -> str:
    """Return the effective base URL, overridable by settings cloud_endpoints/<id>."""
    prov = get_provider(provider_id)
    if settings is not None:
        override = settings.get_string(f"cloud_endpoints/{provider_id}")
        if override:
            return override
    return prov.base_url
