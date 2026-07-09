"""Fetch, cache, refresh, clear, and select external provider models."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, Slot
from justllama.server.providers import get_provider, provider_base_url
from justllama.server.client import LlamaClient
from justllama.config.settings import AppSettings
from justllama.server.providers import get_provider, provider_base_url, PROVIDER_IDS

_CACHE_KEY = "cloud_models/{}"   # per-provider QSettings key (mirrors mcp/servers list pattern)


class _FetchRunner(QThread):
    finished = Signal(str, list)   # provider_id, model id list
    error = Signal(str, str)       # provider_id, message

    def __init__(self, provider_id: str, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._pid = provider_id
        self._settings = settings

    def run(self):
        try:
            key = self._settings.get_api_key(self._pid)
            if not key:
                self.error.emit(self._pid, "API key not configured")
                return
            base = provider_base_url(self._pid, self._settings)
            client = LlamaClient(base_url=base, api_key=key)
            data = client.models()                       # list of {"id": ...}
            ids = [m["id"] for m in data if isinstance(m, dict) and m.get("id")]
            if not ids:
                self.error.emit(self._pid, "No models returned by provider")
                return
            self.finished.emit(self._pid, ids)
        except Exception as e:
            self.error.emit(self._pid, str(e))


class ExternalModelsManager(QObject):
    models_fetched = Signal(str, list)   # provider_id, ids  (also persisted to cache here)
    models_error = Signal(str, str)      # provider_id, message
    cache_cleared = Signal(str)          # provider_id

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._runner = None

    @Slot(str)
    def refresh(self, provider_id: str):
        """Fetch live model list from the provider (network, off-thread)."""
        try:
            get_provider(provider_id)  # raises ValueError on unknown id
        except ValueError as e:
            self.models_error.emit(provider_id, str(e))
            return
        runner = _FetchRunner(provider_id, self._settings, self)
        runner.finished.connect(self._on_fetched)
        runner.error.connect(self.models_error)
        runner.finished.connect(runner.deleteLater)
        runner.error.connect(runner.deleteLater)
        runner.start()
        self._runner = runner

    @Slot(str, list)
    def _on_fetched(self, provider_id: str, ids: list):
        self._settings.set_list(_CACHE_KEY.format(provider_id), ids)
        self.models_fetched.emit(provider_id, ids)

    @Slot(str, result=list)
    def get_cached_models(self, provider_id: str) -> list:
        """Return the persisted cache (empty if none). Used to populate UI on open."""
        return self._settings.get_list(_CACHE_KEY.format(provider_id))

    @Slot(str)
    def clear_cache(self, provider_id: str):
        """Drop the persisted cache for one provider."""
        self._settings.set_list(_CACHE_KEY.format(provider_id), [])
        self.cache_cleared.emit(provider_id)

    @Slot(str, int, str)
    def select_model(self, provider_id: str, slot: int, model_id: str):
        """Write `provider:model` into council/model_<slot> (1-based)."""
        if not (1 <= slot <= 3):
            raise ValueError(f"slot must be 1..3, got {slot}")
        self._settings.set_string(f"council/model_{slot}", f"{provider_id}:{model_id}")
