"""Tests for justllama.models.downloader.ModelDownloader.

All tests mock huggingface_hub to avoid network calls and _DownloadThread
to avoid actual QThread lifecycle issues.
"""

from unittest.mock import MagicMock, patch

import pytest

from justllama.models.downloader import ModelDownloader, _DownloadThread


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def qapp():
    """Ensure a QCoreApplication exists (PySide6 QObject requirement)."""
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def downloader(qapp):
    """ModelDownloader with a temporary directory."""
    return ModelDownloader(models_dir="/tmp/test_models")


@pytest.fixture
def mock_thread():
    """Mock _DownloadThread that doesn't actually start."""
    mock = MagicMock(spec=_DownloadThread)
    mock.isRunning.return_value = False
    mock.start.return_value = True
    return mock


# ---------------------------------------------------------------------------
# set_directory() tests
# ---------------------------------------------------------------------------

class TestSetDirectory:
    def test_sets_download_directory(self, downloader, tmp_path):
        """set_directory updates the internal directory path."""
        new_dir = str(tmp_path / "new_models")
        downloader.set_directory(new_dir)
        assert downloader._dir == new_dir

    def test_directory_used_for_subsequent_downloads(self, downloader, tmp_path):
        """After set_directory, the new directory is passed to _DownloadThread."""
        new_dir = str(tmp_path / "custom_models")
        downloader.set_directory(new_dir)

        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            # _DownloadThread constructor: (repo_id, filename, local_dir, parent)
            call_args = MockThread.call_args
            assert call_args[0][2] == new_dir


# ---------------------------------------------------------------------------
# download() tests
# ---------------------------------------------------------------------------

class TestDownload:
    def test_returns_true_when_download_starts(self, downloader):
        """download() returns True when a download is successfully started."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                result = downloader.download("TheBloke/Llama-2-7B-GGUF")

            assert result is True

    def test_returns_false_if_already_downloading(self, downloader):
        """download() returns False when a download is already in progress."""
        mock_instance = MagicMock()
        mock_instance.isRunning.return_value = True
        downloader._thread = mock_instance

        result = downloader.download("TheBloke/Llama-2-7B-GGUF")
        assert result is False

    def test_returns_false_when_disk_space_insufficient(self, downloader):
        """download() returns False when free disk space is below 1 GB."""
        with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(free=500_000_000)  # 500 MB
            result = downloader.download("TheBloke/Llama-2-7B-GGUF")

        assert result is False

    def test_returns_true_when_disk_usage_raises_oserror(self, downloader):
        """download() proceeds when disk_usage raises OSError (dir may not exist)."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.side_effect = OSError("No such directory")
                result = downloader.download("TheBloke/Llama-2-7B-GGUF")

            assert result is True

    def test_emits_download_started_signal(self, downloader):
        """download() emits download_started with the target filename."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)

                spy = MagicMock()
                downloader.download_started.connect(spy)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            spy.assert_called_once_with("TheBloke/Llama-2-7B-GGUF")

    def test_emits_download_started_with_filename_when_specified(self, downloader):
        """download() emits download_started with filename when provided."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)

                spy = MagicMock()
                downloader.download_started.connect(spy)
                downloader.download("TheBloke/Llama-2-7B-GGUF", "model.gguf")

            spy.assert_called_once_with("model.gguf")

    def test_emits_download_error_when_already_downloading(self, downloader):
        """download() emits download_error when a download is already running."""
        mock_instance = MagicMock()
        mock_instance.isRunning.return_value = True
        downloader._thread = mock_instance

        spy = MagicMock()
        downloader.download_error.connect(spy)
        downloader.download("TheBloke/Llama-2-7B-GGUF")

        spy.assert_called_once()
        args = spy.call_args[0]
        assert args[0] == "TheBloke/Llama-2-7B-GGUF"
        assert "already in progress" in args[1]

    def test_emits_download_error_when_disk_full(self, downloader):
        """download() emits download_error with disk space message."""
        with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(free=500_000_000)

            spy = MagicMock()
            downloader.download_error.connect(spy)
            downloader.download("TheBloke/Llama-2-7B-GGUF", "model.gguf")

        spy.assert_called_once()
        args = spy.call_args[0]
        assert args[0] == "model.gguf"
        assert "Insufficient disk space" in args[1]

    def test_calls_thread_with_correct_params(self, downloader):
        """download() creates _DownloadThread with correct arguments."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF", "model.gguf")

            MockThread.assert_called_once_with(
                "TheBloke/Llama-2-7B-GGUF",
                "model.gguf",
                "/tmp/test_models",
                downloader,
            )

    def test_thread_is_started(self, downloader):
        """download() calls start() on the created thread."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            mock_instance.start.assert_called_once()

    def test_thread_signals_connected(self, downloader):
        """download() connects thread signals to internal handlers."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            mock_instance.finished.connect.assert_called_once_with(downloader._on_finished)
            mock_instance.error.connect.assert_called_once_with(downloader._on_error)

    def test_stores_thread_reference(self, downloader):
        """download() stores the thread reference for later is_downloading checks."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            assert downloader._thread is mock_instance

    def test_default_filename_is_empty(self, downloader):
        """download() uses empty string as default filename."""
        with patch("justllama.models.downloader._DownloadThread") as MockThread:
            mock_instance = MagicMock()
            MockThread.return_value = mock_instance
            mock_instance.isRunning.return_value = False

            with patch("justllama.models.downloader.shutil.disk_usage") as mock_usage:
                mock_usage.return_value = MagicMock(free=10_000_000_000)
                downloader.download("TheBloke/Llama-2-7B-GGUF")

            call_args = MockThread.call_args
            assert call_args[0][1] == ""  # filename is empty string


# ---------------------------------------------------------------------------
# is_downloading() tests
# ---------------------------------------------------------------------------

class TestIsDownloading:
    def test_returns_false_when_idle(self, downloader):
        """is_downloading() returns False when no download has started."""
        assert downloader.is_downloading() is False

    def test_returns_false_when_thread_not_running(self, downloader):
        """is_downloading() returns False when thread exists but not running."""
        mock_instance = MagicMock()
        mock_instance.isRunning.return_value = False
        downloader._thread = mock_instance

        assert downloader.is_downloading() is False

    def test_returns_true_when_download_thread_is_running(self, downloader):
        """is_downloading() returns True when a download thread is running."""
        mock_instance = MagicMock()
        mock_instance.isRunning.return_value = True
        downloader._thread = mock_instance

        assert downloader.is_downloading() is True

    def test_returns_false_when_thread_is_none(self, downloader):
        """is_downloading() returns False when _thread is None."""
        downloader._thread = None
        assert downloader.is_downloading() is False


# ---------------------------------------------------------------------------
# Signal forwarding tests
# ---------------------------------------------------------------------------

class TestSignals:
    def test_download_finished_emits_filename_and_path(self, downloader):
        """_on_finished forwards (filename, path) to download_finished signal."""
        spy = MagicMock()
        downloader.download_finished.connect(spy)

        downloader._on_finished("model.gguf", "/tmp/models/model.gguf")

        spy.assert_called_once_with("model.gguf", "/tmp/models/model.gguf")

    def test_download_error_emits_filename_and_error(self, downloader):
        """_on_error forwards (filename, error) to download_error signal."""
        spy = MagicMock()
        downloader.download_error.connect(spy)

        downloader._on_error("model.gguf", "Network timeout")

        spy.assert_called_once_with("model.gguf", "Network timeout")

    def test_download_started_emits_filename(self, downloader):
        """download_started signal emits the target filename."""
        spy = MagicMock()
        downloader.download_started.connect(spy)

        downloader.download_started.emit("model.gguf")

        spy.assert_called_once_with("model.gguf")


# ---------------------------------------------------------------------------
# Full download lifecycle with mock huggingface_hub
# ---------------------------------------------------------------------------

class TestDownloadLifecycle:
    def test_hf_hub_download_called_with_correct_params(self, qapp, tmp_path):
        """_DownloadThread.run() calls hf_hub_download with expected arguments."""
        mock_hf_download = MagicMock(return_value=str(tmp_path / "model.gguf"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_hf_download)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="model.gguf",
                local_dir=str(tmp_path),
            )
            # Manually run the thread's logic (avoid actual QThread.start)
            thread.run()

        mock_hf_download.assert_called_once_with(
            repo_id="TheBloke/Llama-2-7B-GGUF",
            filename="model.gguf",
            local_dir=str(tmp_path),
        )

    def test_snapshot_download_called_when_no_filename(self, qapp, tmp_path):
        """_DownloadThread.run() calls snapshot_download when filename is empty."""
        mock_snapshot = MagicMock(return_value=str(tmp_path))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(snapshot_download=mock_snapshot)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="",
                local_dir=str(tmp_path),
            )
            thread.run()

        mock_snapshot.assert_called_once_with(
            repo_id="TheBloke/Llama-2-7B-GGUF",
            local_dir=str(tmp_path),
        )

    def test_download_thread_emits_finished_on_success(self, qapp, tmp_path):
        """_DownloadThread emits finished signal with filename and path on success."""
        mock_hf_download = MagicMock(return_value=str(tmp_path / "model.gguf"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_hf_download)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="model.gguf",
                local_dir=str(tmp_path),
            )

            spy_finished = MagicMock()
            thread.finished.connect(spy_finished)
            thread.run()

        spy_finished.assert_called_once_with("model.gguf", str(tmp_path / "model.gguf"))

    def test_download_thread_emits_error_on_failure(self, qapp, tmp_path):
        """_DownloadThread emits error signal when download fails."""
        mock_hf_download = MagicMock(side_effect=Exception("Connection refused"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_hf_download)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="model.gguf",
                local_dir=str(tmp_path),
            )

            spy_error = MagicMock()
            thread.error.connect(spy_error)
            thread.run()

        spy_error.assert_called_once_with("model.gguf", "Connection refused")

    def test_download_thread_creates_local_dir(self, qapp, tmp_path):
        """_DownloadThread creates the local directory if it doesn't exist."""
        target_dir = tmp_path / "subdir" / "models"
        mock_hf_download = MagicMock(return_value=str(target_dir / "model.gguf"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_hf_download)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="model.gguf",
                local_dir=str(target_dir),
            )
            thread.run()

        assert target_dir.exists()

    def test_download_thread_snapshot_uses_repo_id_as_target(self, qapp, tmp_path):
        """_DownloadThread emits finished with repo_id as target when no filename."""
        mock_snapshot = MagicMock(return_value=str(tmp_path))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(snapshot_download=mock_snapshot)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="",
                local_dir=str(tmp_path),
            )

            spy_finished = MagicMock()
            thread.finished.connect(spy_finished)
            thread.run()

        spy_finished.assert_called_once_with("TheBloke/Llama-2-7B-GGUF", str(tmp_path))

    def test_download_thread_error_uses_filename_as_target(self, qapp, tmp_path):
        """_DownloadThread emits error with filename as target when filename given."""
        mock_hf_download = MagicMock(side_effect=Exception("fail"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(hf_hub_download=mock_hf_download)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="model.gguf",
                local_dir=str(tmp_path),
            )

            spy_error = MagicMock()
            thread.error.connect(spy_error)
            thread.run()

        spy_error.assert_called_once_with("model.gguf", "fail")

    def test_download_thread_error_uses_repo_id_when_no_filename(self, qapp, tmp_path):
        """_DownloadThread emits error with repo_id as target when filename empty."""
        mock_snapshot = MagicMock(side_effect=Exception("fail"))

        with patch.dict("sys.modules", {"huggingface_hub": MagicMock(snapshot_download=mock_snapshot)}):
            thread = _DownloadThread(
                repo_id="TheBloke/Llama-2-7B-GGUF",
                filename="",
                local_dir=str(tmp_path),
            )

            spy_error = MagicMock()
            thread.error.connect(spy_error)
            thread.run()

        spy_error.assert_called_once_with("TheBloke/Llama-2-7B-GGUF", "fail")
