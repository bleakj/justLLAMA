"""Tests for justllama.rag.embeddings (cloud embedding backend, WS2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from justllama.rag.embeddings import (
    CloudEmbedder,
    EMBEDDING_PROVIDERS,
    provider_supports_embeddings,
)


class _FakeSettings:
    def __init__(self, values):
        self._values = values

    def get_string(self, key):
        return self._values.get(key, "")


def test_supported_providers():
    assert provider_supports_embeddings("nvidia")
    assert provider_supports_embeddings("gemini")
    assert not provider_supports_embeddings("openrouter")
    assert not provider_supports_embeddings("opencode")
    assert not provider_supports_embeddings("kilocode")
    assert set(EMBEDDING_PROVIDERS) == {"nvidia", "gemini"}


def test_from_settings_returns_none_when_backend_local():
    s = _FakeSettings({"rag/embeddings_backend": "local"})
    assert CloudEmbedder.from_settings(s) is None


def test_from_settings_returns_none_for_unsupported_provider():
    s = _FakeSettings({
        "rag/embeddings_backend": "cloud",
        "rag/embeddings_provider": "openrouter",
        "rag/embeddings_model": "some-model",
    })
    assert CloudEmbedder.from_settings(s) is None


def test_from_settings_returns_none_when_no_key():
    s = _FakeSettings({
        "rag/embeddings_backend": "cloud",
        "rag/embeddings_provider": "nvidia",
        "rag/embeddings_model": "nv-embed",
    })
    with patch("justllama.rag.embeddings.get_api_key", return_value=""):
        assert CloudEmbedder.from_settings(s) is None


def test_from_settings_builds_embedder_with_key():
    s = _FakeSettings({
        "rag/embeddings_backend": "cloud",
        "rag/embeddings_provider": "nvidia",
        "rag/embeddings_model": "nv-embed",
    })
    with patch("justllama.rag.embeddings.get_api_key", return_value="secret"):
        embedder = CloudEmbedder.from_settings(s)
    assert embedder is not None
    assert embedder.provider == "nvidia"
    assert embedder.model == "nv-embed"


def test_embed_calls_client_embeddings():
    with patch("justllama.rag.embeddings.get_api_key", return_value="secret"):
        embedder = CloudEmbedder("gemini", "text-embedding-004")
    embedder._client = MagicMock()
    embedder._client.embeddings.return_value = [[0.1], [0.2]]
    out = embedder.embed(["a", "b"])
    embedder._client.embeddings.assert_called_once_with(["a", "b"], model="text-embedding-004")
    assert out == [[0.1], [0.2]]


def test_embed_empty_returns_empty():
    with patch("justllama.rag.embeddings.get_api_key", return_value="secret"):
        embedder = CloudEmbedder("gemini", "text-embedding-004")
    assert embedder.embed([]) == []


def test_constructor_rejects_unsupported_provider():
    with pytest.raises(ValueError):
        CloudEmbedder("openrouter", "m", api_key="x")


def test_constructor_rejects_missing_model():
    with pytest.raises(ValueError):
        CloudEmbedder("nvidia", "", api_key="x")
