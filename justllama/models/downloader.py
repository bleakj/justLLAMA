"""HuggingFace Hub model downloader with progress reporting."""

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _DownloadThread(QThread):
    """Background thread for downloading models from HuggingFace."""

    progress = Signal(str, float, str)  # filename, fraction, status_msg
    finished = Signal(str, str)  # filename, local_path
    error = Signal(str, str)  # filename, error_message

    def __init__(self, repo_id, filename, local_dir, parent=None):
        super().__init__(parent)
        self._repo_id = repo_id
        self._filename = filename
        self._local_dir = local_dir

    def run(self):
        try:
            from huggingface_hub import hf_hub_download, snapshot_download

            local_dir = Path(self._local_dir)
            local_dir.mkdir(parents=True, exist_ok=True)

            if self._filename:
                self.progress.emit(self._filename, 0.0, "Starting download...")
                path = hf_hub_download(
                    repo_id=self._repo_id,
                    filename=self._filename,
                    local_dir=str(local_dir),
                )
                self.finished.emit(self._filename, str(path))
            else:
                self.progress.emit(self._repo_id, 0.0, "Downloading snapshot...")
                path = snapshot_download(
                    repo_id=self._repo_id,
                    local_dir=str(local_dir),
                )
                self.finished.emit(self._repo_id, str(path))

        except Exception as e:
            target = self._filename or self._repo_id
            self.error.emit(target, str(e))


class ModelDownloader(QObject):
    """Downloads GGUF models from HuggingFace Hub.

    Signals:
        download_started(str filename)
        download_progress(str filename, float progress, str message)
        download_finished(str filename, str path)
        download_error(str filename, str error)
    """

    download_started = Signal(str)
    download_progress = Signal(str, float, str)
    download_finished = Signal(str, str)
    download_error = Signal(str, str)

    def __init__(self, models_dir: str = "", parent=None):
        super().__init__(parent)
        self._dir = models_dir or str(
            Path.home() / "Documents" / "models"
        )
        self._thread: _DownloadThread | None = None

    @Slot(str)
    def set_directory(self, path: str):
        self._dir = path

    @Slot(str, str, result=bool)
    def download(self, repo_id: str, filename: str = "") -> bool:
        """Start downloading a model from HuggingFace.

        Args:
            repo_id: HuggingFace repo (e.g., "TheBloke/Llama-2-7B-GGUF").
            filename: Specific file to download (optional, downloads entire repo if empty).

        Returns:
            True if download started, False if already downloading.
        """
        if self._thread and self._thread.isRunning():
            self.download_error.emit(repo_id, "A download is already in progress")
            return False

        # Disk space check
        target = filename or repo_id
        try:
            usage = shutil.disk_usage(self._dir)
            if usage.free < 1_000_000_000:  # Less than 1GB free
                self.download_error.emit(
                    target,
                    f"Insufficient disk space: {usage.free // (1024**3)}GB free",
                )
                return False
        except OSError:
            pass  # Directory might not exist yet

        self._thread = _DownloadThread(repo_id, filename, self._dir, self)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.progress.connect(self.download_progress)
        self._thread.start()

        self.download_started.emit(target)
        return True

    def _on_finished(self, target: str, path: str):
        self.download_finished.emit(target, path)

    def _on_error(self, target: str, error: str):
        self.download_error.emit(target, error)

    @Slot(result=bool)
    def is_downloading(self) -> bool:
        return self._thread is not None and self._thread.isRunning()
