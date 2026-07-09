"""Scan local directory for GGUF model files."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, Property


@dataclass
class ModelInfo:
    name: str
    path: str
    size_bytes: int
    modified_time: float  # epoch seconds

    @property
    def size_display(self) -> str:
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024**3)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "size_display": self.size_display,
            "size_gb": self.size_gb,
            "modified_time": self.modified_time,
        }


class ModelBrowser(QObject):
    """Browses local GGUF model files.

    Signals:
        models_changed(list[dict]) — emitted after scan.
    """

    models_changed = Signal(list)  # list of dicts

    @Property(float, constant=True)
    def safe_ram_gb(self) -> float:
        try:
            total_ram = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024**3)
        except (AttributeError, ValueError):
            total_ram = 0.0
        return max(0.0, total_ram - 8.0)  # 8 GB system buffer

    @Property(float, constant=True)
    def safe_vram_gb(self) -> float:
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, check=True, timeout=5
            )
            total_vram = int(result.stdout.strip().split('\n')[0]) / 1024.0
        except Exception:
            total_vram = 0.0
        return max(0.0, total_vram - 1.5)  # 1.5 GB VRAM buffer

    def __init__(self, models_dir: str = "", parent=None):
        super().__init__(parent)
        self._dir = Path(models_dir) if models_dir else (
            Path.home() / "Documents" / "models"
        )

    @Slot(str)
    def set_directory(self, path: str):
        self._dir = Path(path)

    @Slot(result=str)
    def directory(self) -> str:
        return str(self._dir)

    @Slot(result=list)
    def scan(self) -> list[dict]:
        """Scan the models directory for .gguf files."""
        models = []
        if not self._dir.is_dir():
            self.models_changed.emit(models)
            return models

        seen = set()
        for pattern in ("*.gguf", "*.gguf.part*"):
            for f in sorted(self._dir.glob(pattern)):
                try:
                    resolved = f.resolve()
                    stat = f.stat()
                except (OSError, PermissionError):
                    # Broken symlink or unreadable file — skip safely.
                    continue
                # Skip mmproj files (multimodal projectors, not standalone models)
                if f.name.startswith("mmproj"):
                    continue
                models.append(ModelInfo(
                    name=f.stem,
                    path=str(f),
                    size_bytes=stat.st_size,
                    modified_time=stat.st_mtime,
                ).to_dict())

        self.models_changed.emit(models)
        return models

    @Slot(str, result=dict)
    def get_model(self, path: str) -> dict:
        """Get info for a specific model file.

        Returns an empty dict when the file does not exist — ``None`` is
        awkward to surface across QML and risks nil-property crashes.
        """
        p = Path(path)
        if not p.is_file():
            return {}
        stat = p.stat()
        return ModelInfo(
            name=p.stem,
            path=str(p),
            size_bytes=stat.st_size,
            modified_time=stat.st_mtime,
        ).to_dict()
