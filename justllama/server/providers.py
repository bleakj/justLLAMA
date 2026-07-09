"""External API partner definitions for cloud model routing."""
from dataclasses import dataclass

from justllama.config.env import _PROVIDER_ENV  # provider -> env var map


@dataclass(frozen=True)
class Provider:
    id: str            # "nvidia" | "openrouter" | "opencode"  (matches council prefix)
    label: str         # Human label for UI, e.g. "NVIDIA"
    base_url: str      # OpenAI-compatible /v1 base; may be overridden at runtime
    env_var: str       # API key env var name (from _PROVIDER_ENV)


# Static base URLs (opencode's is overridable via cloud_endpoints/opencode at runtime).
_PROVIDERS = {
    "nvidia": Provider("nvidia", "NVIDIA", "https://integrate.api.nvidia.com", _PROVIDER_ENV["nvidia"]),
    "openrouter": Provider("openrouter", "OpenRouter", "https://openrouter.ai/api", _PROVIDER_ENV["openrouter"]),
    "opencode": Provider("opencode", "Opencode", "https://api.opencode.com", _PROVIDER_ENV["opencode"]),
}
PROVIDER_IDS = tuple(_PROVIDERS.keys())


def get_provider(provider_id: str) -> Provider:
    if provider_id not in _PROVIDERS:
        raise ValueError(f"Unknown API provider: {provider_id!r}")
    return _PROVIDERS[provider_id]


def provider_base_url(provider_id: str, settings) -> str:
    """Return the effective base URL; opencode may be overridden by settings."""
    prov = get_provider(provider_id)
    if provider_id == "opencode" and settings is not None:
        return settings.get_string("cloud_endpoints/opencode") or prov.base_url
    return prov.base_url
