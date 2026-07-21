"""Per-model configuration profiles stored as JSON on disk."""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


_PROFILES_DIR = Path.home() / ".config" / "justllama" / "profiles"


class ModelProfiles(QObject):
    """Manages named configuration profiles for server settings.

    Signals:
        profiles_changed()
    """

    profiles_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_").replace("..", "_")
        return _PROFILES_DIR / f"{safe}.json"
    @Slot(str, str, result=bool)
    def save_profile(self, name: str, config_json: str) -> bool:
        """Save a profile. config_json is a JSON string of settings dict."""
        try:
            config = json.loads(config_json)
        except json.JSONDecodeError:
            return False
        try:
            self._path_for(name).write_text(json.dumps(config, indent=2))
            self.profiles_changed.emit()
            return True
        except OSError:
            return False

    @Slot(str, result=str)
    def load_profile(self, name: str) -> str:
        """Load a profile, returns JSON string or empty string."""
        path = self._path_for(name)
        if path.is_file():
            try:
                return path.read_text()
            except OSError:
                pass
        # Fallback to model filename if name was a full path
        if "/" in name or "\\" in name:
            alt_path = self._path_for(Path(name).name)
            if alt_path.is_file():
                try:
                    return alt_path.read_text()
                except OSError:
                    pass
        return ""

    @Slot(str, result=dict)
    def get_model_profile(self, model_path: str) -> dict:
        """Get model profile as a dictionary for a given model path."""
        raw = self.load_profile(model_path)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @Slot(str, str, result=bool)
    def save_model_profile(self, model_path: str, config_json: str) -> bool:
        """Save a profile JSON string for a given model path."""
        return self.save_profile(model_path, config_json)

    def get_effective_config(self, model_path: str, global_settings=None) -> dict:
        """Return merged config dictionary (global defaults overridden by model profile)."""
        eff = {
            "binary": global_settings.get_string("server/binary") if global_settings else "llama-server",
            "port": global_settings.get_int("server/port") if (global_settings and global_settings.get_int("server/port")) else 8080,
            "model_path": model_path,
            "ctx_size": global_settings.get_int("server/ctx_size") if (global_settings and global_settings.get_int("server/ctx_size")) else 4096,
            "n_gpu_layers": global_settings.get_int("server/n_gpu_layers") if (global_settings and global_settings.get_int("server/n_gpu_layers") is not None) else "auto",
            "threads": global_settings.get_int("server/threads") if global_settings else -1,
            "batch_size": global_settings.get_int("server/batch_size") if (global_settings and global_settings.get_int("server/batch_size")) else 512,
            "ubatch_size": global_settings.get_int("server/ubatch_size") if (global_settings and global_settings.get_int("server/ubatch_size")) else 512,
            "flash_attn": global_settings.get_bool("server/flash_attn") if global_settings else True,
            "mmap": global_settings.get_bool("server/mmap") if global_settings else True,
            "mlock": global_settings.get_bool("server/mlock") if global_settings else False,
            "cache_type_k": global_settings.get_string("server/cache_type_k") if global_settings else "",
            "cache_type_v": global_settings.get_string("server/cache_type_v") if global_settings else "",
            "cpu_moe": global_settings.get_bool("server/cpu_moe") if global_settings else False,
            "n_cpu_moe": global_settings.get_int("server/n_cpu_moe") if global_settings else 0,
            "model_draft": global_settings.get_string("server/model_draft") if global_settings else "",
            "gpu_layers_draft": global_settings.get_int("server/gpu_layers_draft") if (global_settings and global_settings.get_int("server/gpu_layers_draft")) else 99,
            "draft_max": global_settings.get_int("server/draft_max") if global_settings else 0,
            "draft_min": global_settings.get_int("server/draft_min") if global_settings else 0,
            "jinja": False,
            "chat_template": "",
            "extra_args": [],
        }
        profile = self.get_model_profile(model_path)
        for k, v in profile.items():
            if v is not None and v != "":
                eff[k] = v
        return eff

    @Slot(str, QObject, result=str)
    def get_effective_config_json(self, model_path: str, global_settings=None) -> str:
        """Return merged config as a JSON string for QML consumption."""
        eff = self.get_effective_config(model_path, global_settings)
        return json.dumps(eff)
    @Slot(result=list)
    def list_profiles(self) -> list[str]:
        """List all profile names."""
        return sorted(
            p.stem for p in _PROFILES_DIR.glob("*.json")
        )

    @Slot(str, result=bool)
    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name."""
        path = self._path_for(name)
        if path.is_file():
            try:
                path.unlink()
                self.profiles_changed.emit()
                return True
            except OSError:
                return False
        return False
