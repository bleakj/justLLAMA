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
        safe = name.replace("/", "_").replace("..", "_")
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
        if not path.is_file():
            return ""
        try:
            return path.read_text()
        except OSError:
            return ""

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
