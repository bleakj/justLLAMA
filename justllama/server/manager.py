"""llama-server process lifecycle management."""

import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _ServerLogReader(QThread):
    """Read stdout/stderr from the subprocess in a background thread."""

    line_read = Signal(str)

    def __init__(self, stream, parent=None):
        super().__init__(parent)
        self._stream = stream
        self._running = True

    def run(self):
        while self._running:
            line = self._stream.readline()
            if not line:
                break
            self.line_read.emit(line.rstrip("\n"))

    def stop(self):
        self._running = False


class ServerManager(QObject):
    """Manages the llama-server subprocess lifecycle.

    Signals:
        server_started(int port)
        server_stopped()
        server_error(str message)
        log_line(str line)
    """

    server_started = Signal(int)
    server_stopped = Signal()
    server_error = Signal(str)
    log_line = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._stdout_reader: _ServerLogReader | None = None
        self._stderr_reader: _ServerLogReader | None = None
        self._port = 8080

    @Slot(result=bool)
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @Slot(str, str, int, int, int, int, result=bool)
    def start(self, binary: str, model_path: str, port: int = 8080,
              ctx_size: int = 4096, n_gpu_layers: int = 99,
              threads: int = -1) -> bool:
        """Start the llama-server process.

        Args:
            binary: Path to llama-server binary.
            model_path: Path to GGUF model file.
            port: Port to listen on.
            ctx_size: Context window size.
            n_gpu_layers: Number of layers to offload to GPU.
            threads: Number of CPU threads (-1 = auto).

        Returns:
            True if started successfully, False otherwise.
        """
        if self.is_running():
            self.log_line.emit("Server already managed by us, stopping first...")
            self.stop()

        # Kill any process occupying the target port (e.g. stray llama-server)
        self._kill_port(port)

        # Validate binary
        if not shutil.which(binary) and not Path(binary).is_file():
            self.server_error.emit(f"llama-server binary not found: {binary}")
            return False

        # Validate model
        if not Path(model_path).is_file():
            self.server_error.emit(f"Model file not found: {model_path}")
            return False

        # Build command
        cmd = [
            binary,
            "--model", model_path,
            "--port", str(port),
            "--ctx-size", str(ctx_size),
            "--n-gpu-layers", str(n_gpu_layers),
        ]
        if threads > 0:
            cmd.extend(["--threads", str(threads)])

        # Set env so shared libs next to the binary are found (CUDA, etc.)
        import os
        env = os.environ.copy()
        bin_dir = str(Path(binary).parent)
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{bin_dir}:{existing}" if existing else bin_dir

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError as e:
            self.server_error.emit(f"Failed to start server: {e}")
            return False

        self._port = port

        # Start log readers
        self._stdout_reader = _ServerLogReader(self._process.stdout, self)
        self._stdout_reader.line_read.connect(self.log_line)
        self._stderr_reader = _ServerLogReader(self._process.stderr, self)
        self._stderr_reader.line_read.connect(self.log_line)
        self._stdout_reader.start()
        self._stderr_reader.start()
        # Wait for server to be healthy (model loading can take seconds)
        import urllib.request
        health_url = f"http://127.0.0.1:{port}/health"
        for attempt in range(30):
            time.sleep(1)
            if self._process.poll() is not None:
                self.server_error.emit(
                    f"Server exited with code {self._process.returncode}"
                )
                self._cleanup()
                return False
            try:
                resp = urllib.request.urlopen(health_url, timeout=2)
                if resp.status == 200:
                    self.server_started.emit(port)
                    return True
            except Exception:
                pass
        self.server_error.emit("Server did not become healthy within 30s")
        self._cleanup()
        return False

    @Slot(result=bool)
    def stop(self) -> bool:
        """Stop the server with SIGTERM → wait 5s → SIGKILL."""
        if not self.is_running():
            self.server_stopped.emit()
            return True

        try:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
        except (ProcessLookupError, OSError):
            pass  # Already dead

        self._cleanup()
        self.server_stopped.emit()
        return True

    @Slot(result=bool)
    def restart(self) -> bool:
        """Restart the server."""
        # Save current config before stopping
        self.stop()
        # Caller should call start() again after this returns
        return True

    @Slot(result=int)
    def port(self) -> int:
        return self._port

    def _cleanup(self):
        """Clean up log readers and process reference."""
        if self._stdout_reader:
            self._stdout_reader.stop()
            self._stdout_reader.wait(2000)
            self._stdout_reader = None
        if self._stderr_reader:
            self._stderr_reader.stop()
            self._stderr_reader.wait(2000)
            self._stderr_reader = None
        self._process = None
    def _kill_port(self, port: int):
        """Kill any process listening on the given port (Linux)."""
        try:
            import socket
            # Check if port is in use
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result != 0:
                return  # Port is free

            # Port in use — find and kill the process
            self.log_line.emit(f"Port {port} is occupied, killing existing process...")
            import subprocess
            # Find PID using the port
            out = subprocess.run(
                ["fuser", str(port) + "/tcp"],
                capture_output=True, text=True, timeout=5
            )
            for pid_str in out.stdout.split():
                pid = int(pid_str)
                self.log_line.emit(f"Killing PID {pid} on port {port}")
                try:
                    import os
                    os.kill(pid, 15)  # SIGTERM
                    time.sleep(1)
                    # Force kill if still alive
                    os.kill(pid, 0)  # Check if alive
                    os.kill(pid, 9)  # SIGKILL
                except (ProcessLookupError, PermissionError):
                    pass
            time.sleep(1)
        except Exception as e:
            self.log_line.emit(f"Port cleanup warning: {e}")
