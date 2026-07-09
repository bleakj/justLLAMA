"""QSettings-based application configuration."""

from pathlib import Path

from PySide6.QtCore import QSettings, QObject, Signal, Slot


class AppSettings(QObject):
    """Persistent application settings via QSettings.

    Organization: justllama, Application: justllama.
    """

    settings_changed = Signal(str, 'QVariant')  # key, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._s = QSettings("justllama", "justllama")
        # Set defaults on first run
        self._set_defaults()

    def _set_defaults(self):
        defaults = {
            "server/binary": str(Path.home() / ".local" / "bin" / "llama-server-cuda"),
            "server/port": 8080,
            "server/model_path": "",
            "server/ctx_size": 4096,
            "server/n_gpu_layers": 99,
            "server/threads": -1,
            "server/batch_size": 512,
            "server/flash_attn": True,
            "server/ubatch_size": 512,
            "server/mmap": True,
            "server/mlock": False,
            "server/numa": "",
            "models/directory": str(Path.home() / "Documents" / "models"),
            "rag/enabled": False,
            "rag/chunk_size": 512,
            "rag/chunk_overlap": 50,
            "rag/vectorstore_path": str(
                Path.home() / ".local" / "share" / "justllama" / "vectordb"
            ),
            "memory/enabled": False,
            "memory/db_path": str(
                Path.home() / ".local" / "share" / "justllama" / "memory.db"
            ),
            "memory/max_short_term": 50,
            "chat/mode": "chat",
            "council/model_1": "",
            "council/model_2": "",
            "council/model_3": "",
            "chat/voice_input_enabled": False,
            "chat/voice_model": "base.en",
            "chat/voice_send_automatically": False,
            "mcp/servers": [],
            "cloud_endpoints/opencode": "https://api.opencode.com",
        }
        for key, default in defaults.items():
            if self._s.value(key) is None:
                self._s.setValue(key, default)

    # --- Typed accessors ---

    @Slot(str, result=str)
    def get_string(self, key: str) -> str:
        return str(self._s.value(key, ""))

    @Slot(str, result=int)
    def get_int(self, key: str) -> int:
        return int(self._s.value(key, 0))

    @Slot(str, result=bool)
    def get_bool(self, key: str) -> bool:
        return str(self._s.value(key, "false")).lower() in ("true", "1", "yes")
    @Slot(str, result=list)
    def get_list(self, key: str) -> list:
        val = self._s.value(key, [])
        if val is None:
            return []
        if isinstance(val, list):
            return [str(x) for x in val]
        if isinstance(val, str):
            if not val.strip():
                return []
            return [val]
        return []

    @Slot(str, list)
    def set_list(self, key: str, value: list):
        self._s.setValue(key, value)
        self.settings_changed.emit(key, value)

    @Slot(str, str)
    def set_string(self, key: str, value: str):
        self._s.setValue(key, value)
        self.settings_changed.emit(key, value)

    @Slot(str, int)
    def set_int(self, key: str, value: int):
        self._s.setValue(key, value)
        self.settings_changed.emit(key, value)

    @Slot(str, bool)
    def set_bool(self, key: str, value: bool):
        self._s.setValue(key, value)
        self.settings_changed.emit(key, value)

    # --- Convenience properties ---

    @property
    def server_port(self) -> int:
        return self.get_int("server/port")

    @property
    def model_path(self) -> str:
        return self.get_string("server/model_path")

    @property
    def models_directory(self) -> str:
        return self.get_string("models/directory")

    @property
    def rag_enabled(self) -> bool:
        return self.get_bool("rag/enabled")

    @property
    def memory_enabled(self) -> bool:
        return self.get_bool("memory/enabled")

    @property
    def voice_input_enabled(self) -> bool:
        return self.get_bool("chat/voice_input_enabled")

    @property
    def voice_model(self) -> str:
        return self.get_string("chat/voice_model")

    @property
    def voice_send_automatically(self) -> bool:
        return self.get_bool("chat/voice_send_automatically")
    @property
    def mcp_servers(self) -> list[str]:
        return self.get_list("mcp/servers")

    def get_all_server_config(self) -> dict:
        """Return all server-related settings as a dict."""
        return {
            "binary": self.get_string("server/binary"),
            "model_path": self.get_string("server/model_path"),
            "port": self.get_int("server/port"),
            "ctx_size": self.get_int("server/ctx_size"),
            "n_gpu_layers": self.get_int("server/n_gpu_layers"),
            "threads": self.get_int("server/threads"),
            "batch_size": self.get_int("server/batch_size"),
            "ubatch_size": self.get_int("server/ubatch_size"),
            "flash_attn": self.get_bool("server/flash_attn"),
            "mmap": self.get_bool("server/mmap"),
            "mlock": self.get_bool("server/mlock"),
            "numa": self.get_string("server/numa"),
            "extra_args": [],
        }

    @Slot(str, result=str)
    def get_api_key(self, provider: str) -> str:
        from justllama.config.env import get_api_key
        return get_api_key(provider)

    @Slot(str, str)
    def set_api_key(self, provider: str, value: str):
        from justllama.config.env import set_api_key
        set_api_key(provider, value)
        self.settings_changed.emit(f"api_keys/{provider}", value)
    @Slot()
    def sync(self):
        self._s.sync()
