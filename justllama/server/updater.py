"""llama.cpp updater — check, download, build, install."""

from __future__ import annotations

import shutil
import subprocess
import urllib.request
import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QThread


_GITHUB_API = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
_CURRENT_VERSION = "c0bc8591e"  # tracks installed version (commit hash from b10098 release)


class _CheckWorker(QThread):
    """Background thread: hit GitHub API for latest release."""

    result = Signal(str)  # latest tag name, or "" on error

    def run(self):
        try:
            req = urllib.request.Request(
                _GITHUB_API,
                headers={"Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                tag = data.get("tag_name", "")
                self.result.emit(tag)
        except Exception:
            self.result.emit("")


class _DownloadWorker(QThread):
    """Background thread: download source tarball."""

    progress = Signal(float)  # 0.0 – 1.0
    finished = Signal(str)    # path to downloaded tarball, or "" on error

    def __init__(self, url: str, dest: Path, parent=None):
        super().__init__(parent)
        self._url = url
        self._dest = dest
        self._cancelled = False

    def run(self):
        try:
            req = urllib.request.Request(self._url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 65536
                with open(self._dest, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk or self._cancelled:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(downloaded / total)
            if self._cancelled:
                self._dest.unlink(missing_ok=True)
                self.finished.emit("")
            else:
                self.finished.emit(str(self._dest))
        except Exception:
            self._dest.unlink(missing_ok=True)
            self.finished.emit("")

    def cancel(self):
        self._cancelled = True


class Updater(QObject):
    """Manages llama.cpp update lifecycle.

    States: idle → checking → update_available / up_to_date → downloading → downloaded → installing
    """

    # Signals
    checking = Signal()
    update_available = Signal(str)   # new version tag
    up_to_date = Signal(str)         # current version
    download_started = Signal()
    download_progress = Signal(float)
    download_finished = Signal(str)  # new version tag
    download_error = Signal(str)
    install_started = Signal()
    install_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_version = _CURRENT_VERSION
        self._latest_version = ""
        self._download_path: Path | None = None
        self._check_worker: _CheckWorker | None = None
        self._download_worker: _DownloadWorker | None = None

    # ── Slots ──

    @Slot()
    def check_for_updates(self):
        """Check GitHub for latest llama.cpp release."""
        if self._check_worker and self._check_worker.isRunning():
            return
        self.checking.emit()
        self._check_worker = _CheckWorker(self)
        self._check_worker.result.connect(self._on_check_result)
        self._check_worker.start()

    @Slot()
    def download_update(self):
        """Download the latest release source tarball."""
        if not self._latest_version:
            return
        self.download_started.emit()

        tarball_name = f"llama.cpp-{self._latest_version}.tar.gz"
        url = (
            f"https://github.com/ggerganov/llama.cpp/archive/refs/tags/"
            f"{self._latest_version}.tar.gz"
        )
        dest = Path.home() / ".local" / "share" / "justllama" / "updates"
        dest.mkdir(parents=True, exist_ok=True)
        tarball = dest / tarball_name

        self._download_worker = _DownloadWorker(url, tarball, self)
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()

    @Slot()
    def install_update(self):
        """Close app and trigger rebuild script.

        Writes a small shell script that:
        1. Extracts the downloaded source
        2. Builds with cmake + make
        3. Installs to /usr/local/bin
        4. Relaunches justLLAMA
        Then spawns it detached and exits.
        """
        if not self._download_path or not self._download_path.exists():
            self.install_error.emit("Downloaded file not found")
            return

        self.install_started.emit()

        # Capture the current interpreter so the install script runs against
        # the same Python (handles venvs, system installs, etc.). We embed
        # the resolved path into the script at generation time.
        import sys
        script = self._build_install_script(sys.executable)
        script_path = self._download_path.parent / "install.sh"
        script_path.write_text(script)
        script_path.chmod(0o755)

        # Launch installer detached, then quit
        subprocess.Popen(
            ["bash", str(script_path)],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Exit the app — the installer will relaunch it
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    @Slot(result=str)
    def current_version(self) -> str:
        return self._current_version

    # ── Internal ──

    def _on_check_result(self, tag: str):
        if tag and tag != self._current_version:
            self._latest_version = tag
            self.update_available.emit(tag)
        else:
            self.up_to_date.emit(self._current_version)

    def _on_download_finished(self, path: str):
        if path:
            self._download_path = Path(path)
            self.download_finished.emit(self._latest_version)
        else:
            self.download_error.emit("Download failed")

    def _build_install_script(self, python_exe: str = "python3") -> str:
        tarball = self._download_path
        work_dir = tarball.parent
        tag = self._latest_version
        return f"""#!/usr/bin/env bash
set -euo pipefail

TARBALL="{tarball}"
WORKDIR="{work_dir}"
TAG="{tag}"
APP_DIR="$(dirname "$(readlink -f "$0")")/../.."
PYTHON_EXE="{python_exe}"

echo "=== justLLAMA Updater ==="
echo "Installing llama.cpp $TAG ..."

# Extract
cd "$WORKDIR"
tar xzf "$TARBALL"
cd "llama.cpp-$TAG"

# Build
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)

# Install
sudo cp build/bin/llama-server /usr/local/bin/llama-server
sudo chmod +x /usr/local/bin/llama-server
echo "Installed llama-server $TAG to /usr/local/bin/"

# Clean up
cd "$WORKDIR"
rm -rf "llama.cpp-$TAG" "$TARBALL"

# Relaunch justLLAMA
cd "$APP_DIR"
nohup "$PYTHON_EXE" -m justllama > /dev/null 2>&1 &

echo "Done! justLLAMA will reopen shortly."
"""
