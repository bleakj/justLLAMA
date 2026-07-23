"""QSettings-based application configuration."""

from pathlib import Path

from PySide6.QtCore import QSettings, QObject, Signal, Slot
import json



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
            "server/ctx_size": 0,  # 0 = auto-detect from GGUF metadata
            "server/n_gpu_layers": "auto",  # "auto" = let llama-server detect VRAM
            "server/threads": -1,
            "server/batch_size": 512,
            "server/flash_attn": True,
            "server/ubatch_size": 512,
            "server/mmap": True,
            "server/mlock": False,
            "server/numa": "",
            "server/fit": False,
            "server/cache_type_k": "q8_0",
            "server/cache_type_v": "q8_0",
            "server/cpu_moe": False,
            "server/n_cpu_moe": 0,
            "server/model_draft": "",
            "server/gpu_layers_draft": 99,
            "server/draft_max": 16,
            "server/draft_min": 2,
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
            "skills/user_directory": str(Path.home() / ".local" / "share" / "justllama" / "skills"),
            "cloud_endpoints/opencode": "https://api.opencode.com",
            "ui/theme": "default",
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

    # --- JSON string (complex structured data) ---

    @Slot(str, result=str)
    def get_json_string(self, key: str) -> str:
        val = self._s.value(key, "")
        if val is None:
            return ""
        return str(val)

    @Slot(str, str)
    def set_json_string(self, key: str, value: str):
        self._s.setValue(key, value)
        self.settings_changed.emit(key, value)

    # --- Skills catalog (static, curated) ---

    @Slot(result=str)
    def get_skills_catalog(self) -> str:
        """Return a JSON-serialized list of curated MCP skills."""
        catalog = [
            {
                "id": "maestro",
                "name": "Maestro Workflow",
                "command": "npx -y maestro-workflow-mcp",
                "description": "Provides planning, execution, and memory commands from maestroskills.dev"
            },
            {
                "id": "gemma-dev",
                "name": "Gemma-Dev",
                "command": "python -m justllama.server.gemma_skills_mcp",
                "description": "Official Gemma technical blueprint and ecosystem knowledge"
            },
            {
                "id": "playwright",
                "name": "Playwright Automation",
                "command": "npx -y @playwright/mcp-server",
                "description": "Browser automation and testing"
            },
            {
                "id": "filesystem",
                "name": "Local Filesystem",
                "command": f"npx -y @modelcontextprotocol/server-filesystem {self.models_directory}",
                "description": "Read and write to local directories"
            }
        ]
        return json.dumps(catalog)

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
    @property
    def user_skills_directory(self) -> str:
        return self.get_string("skills/user_directory")

    def get_all_server_config(self) -> dict:
        """Return all server-related settings as a dict."""
        # n_gpu_layers can be "auto" (string) or an integer
        n_gpu_raw = self.get_string("server/n_gpu_layers")
        try:
            n_gpu_layers = int(n_gpu_raw)
        except (ValueError, TypeError):
            n_gpu_layers = n_gpu_raw if n_gpu_raw else "auto"

        return {
            "binary": self.get_string("server/binary"),
            "model_path": self.get_string("server/model_path"),
            "port": self.get_int("server/port"),
            "ctx_size": self.get_int("server/ctx_size"),
            "n_gpu_layers": n_gpu_layers,
            "threads": self.get_int("server/threads"),
            "batch_size": self.get_int("server/batch_size"),
            "ubatch_size": self.get_int("server/ubatch_size"),
            "flash_attn": self.get_bool("server/flash_attn"),
            "mmap": self.get_bool("server/mmap"),
            "mlock": self.get_bool("server/mlock"),
            "numa": self.get_string("server/numa"),
            "cache_type_k": self.get_string("server/cache_type_k"),
            "cache_type_v": self.get_string("server/cache_type_v"),
            "cpu_moe": self.get_bool("server/cpu_moe"),
            "n_cpu_moe": self.get_int("server/n_cpu_moe"),
            "model_draft": self.get_string("server/model_draft"),
            "gpu_layers_draft": self.get_int("server/gpu_layers_draft"),
            "draft_max": self.get_int("server/draft_max"),
            "draft_min": self.get_int("server/draft_min"),
            "spec_type": self.get_string("server/spec_type"),
            "mmproj": self.get_string("server/mmproj"),
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
