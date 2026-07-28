"""Cloud embedding backend for RAG (WS2).

Computes embedding vectors through an OpenAI-compatible ``/v1/embeddings``
endpoint on a configured cloud provider (NVIDIA NIM or Gemini). Reuses the
existing :class:`~justllama.server.client.LlamaClient` transport and the
provider base URLs / ``.env`` keys defined in ``server/providers.py``.

Only NVIDIA and Gemini expose an embeddings API; OpenRouter / Opencode /
Kilocode are chat-only and are rejected here (surfaced in Settings).

The store falls back to local (sentence-transformers / Chroma default)
embeddings whenever cloud embedding is disabled, misconfigured, or fails.
"""

from __future__ import annotations

from justllama.config.env import get_api_key
from justllama.server.client import LlamaClient
from justllama.server.providers import get_provider, provider_base_url

# Providers that offer an OpenAI-compatible embeddings endpoint.
EMBEDDING_PROVIDERS = ("nvidia", "gemini")


def provider_supports_embeddings(provider_id: str) -> bool:
    """True if the given provider exposes an embeddings API."""
    return provider_id in EMBEDDING_PROVIDERS


class CloudEmbedder:
    """Batch-embeds text via a cloud provider's ``/v1/embeddings`` endpoint."""

    def __init__(self, provider: str, model: str, api_key: str | None = None,
                 settings=None):
        if not provider_supports_embeddings(provider):
            raise ValueError(
                f"Provider {provider!r} does not support embeddings "
                f"(supported: {', '.join(EMBEDDING_PROVIDERS)})"
            )
        if not model:
            raise ValueError("An embedding model must be configured")
        prov = get_provider(provider)
        key = api_key if api_key is not None else get_api_key(provider)
        if not key:
            raise ValueError(f"No API key configured for provider {provider!r}")
        self.provider = provider
        self.model = model
        self._client = LlamaClient(
            base_url=provider_base_url(provider, settings),
            api_key=key,
            api_prefix=prov.api_prefix,
        )

    @classmethod
    def from_settings(cls, settings) -> "CloudEmbedder | None":
        """Build a CloudEmbedder from AppSettings, or None if not applicable.

        Returns None (so the caller falls back to local embeddings) when the
        backend is not ``cloud``, the provider is unsupported, or no model /
        API key is configured.
        """
        if settings is None:
            return None
        if settings.get_string("rag/embeddings_backend") != "cloud":
            return None
        provider = settings.get_string("rag/embeddings_provider")
        model = settings.get_string("rag/embeddings_model")
        if not provider_supports_embeddings(provider):
            return None
        try:
            return cls(provider, model, settings=settings)
        except ValueError:
            return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text (order preserved)."""
        if not texts:
            return []
        return self._client.embeddings(texts, model=self.model)
