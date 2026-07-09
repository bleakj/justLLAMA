"""Unit tests for the external provider model manager and provider registry."""

import time

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QSignalSpy

from justllama.config.settings import AppSettings
from justllama.server.external_models import ExternalModelsManager
from justllama.server.providers import get_provider, provider_base_url, PROVIDER_IDS


def _wait_signal(spy, qapp, timeout_ms=5000):
    """Pump the Qt event loop until a threaded signal reaches ``spy``.

    ``QSignalSpy.wait`` is unreliable in headless test runs (no running GUI
    loop), so drive delivery explicitly.
    """
    deadline = timeout_ms / 1000.0
    step = 0.02
    waited = 0.0
    while spy.count() == 0 and waited < deadline:
        qapp.processEvents()
        time.sleep(step)
        waited += step
    return spy.count() > 0


def _temp_settings(qapp, tmp_path, monkeypatch):
    """Return an AppSettings backed by a throwaway temp config file."""
    settings_file = str(tmp_path / "test_settings_external.conf")
    original_init = QSettings.__init__

    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)

    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    return AppSettings()


def test_provider_registry():
    assert get_provider("nvidia").base_url == "https://integrate.api.nvidia.com"
    assert get_provider("openrouter").base_url == "https://openrouter.ai/api"
    assert get_provider("opencode").base_url == "https://api.opencode.com"
    assert get_provider("gemini").base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert get_provider("gemini").api_prefix == ""
    assert get_provider("kilocode").base_url == "https://api.kilocode.com"
    assert get_provider("kilocode").api_prefix == "/v1"
    assert PROVIDER_IDS == ("nvidia", "openrouter", "opencode", "gemini", "kilocode")
    with pytest.raises(ValueError):
        get_provider("bogus")


def test_provider_base_url_opencode_override(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    # Default when not set.
    assert provider_base_url("opencode", settings) == "https://api.opencode.com"
    # Runtime override via settings.
    settings.set_string("cloud_endpoints/opencode", "https://example.com/v1")
    assert provider_base_url("opencode", settings) == "https://example.com/v1"
    # Non-opencode providers ignore the override.
    assert provider_base_url("nvidia", settings) == "https://integrate.api.nvidia.com"


def test_refresh_persists_cache(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    manager = ExternalModelsManager(settings)
    # network bypass: call the persistence path directly (deterministic).
    manager._on_fetched("openrouter", ["a", "b"])
    assert settings.get_list("cloud_models/openrouter") == ["a", "b"]


def test_refresh_thread_persists_cache(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    monkeypatch.setattr(
        "justllama.server.external_models.LlamaClient.models",
        lambda self, timeout=10: [{"id": "a"}, {"id": "b"}],
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    manager = ExternalModelsManager(settings)
    spy = QSignalSpy(manager.models_fetched)
    manager.refresh("openrouter")
    assert _wait_signal(spy, qapp)
    assert settings.get_list("cloud_models/openrouter") == ["a", "b"]


def test_refresh_no_key_emits_error(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    manager = ExternalModelsManager(settings)
    spy = QSignalSpy(manager.models_error)
    manager.refresh("nvidia")
    assert _wait_signal(spy, qapp)
    provider, message = spy.at(0)
    provider = str(provider)
    message = str(message)
    assert provider == "nvidia"
    assert message == "API key not configured"


def test_refresh_unknown_provider_emits_error(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    manager = ExternalModelsManager(settings)
    spy = QSignalSpy(manager.models_error)
    manager.refresh("bogus")  # raises ValueError inside refresh -> wrapped
    assert _wait_signal(spy, qapp)
    provider, message = spy.at(0)
    provider = str(provider)
    message = str(message)
    assert provider == "bogus"
    assert "Unknown API provider" in message
def test_clear_cache(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    manager = ExternalModelsManager(settings)
    manager._on_fetched("openrouter", ["a", "b"])
    assert manager.get_cached_models("openrouter") == ["a", "b"]
    manager.clear_cache("openrouter")
    assert manager.get_cached_models("openrouter") == []
    assert settings.get_list("cloud_models/openrouter") == []


def test_select_model_writes_council_slot(qapp, tmp_path, monkeypatch):
    settings = _temp_settings(qapp, tmp_path, monkeypatch)
    manager = ExternalModelsManager(settings)
    manager.select_model("nvidia", 2, "meta/llama-3")
    assert settings.get_string("council/model_2") == "nvidia:meta/llama-3"
    result = manager.select_model("nvidia", 9, "x")
    assert result == "slot must be 1..3, got 9"
