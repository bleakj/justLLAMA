"""llama-server process lifecycle management."""

import shutil
import signal
import subprocess
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

class _HealthWorker(QThread):
    """Background thread: poll /health until server is ready."""

    success = Signal(int)   # port
    failure = Signal(str)   # error message

    def __init__(self, port: int, process: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._port = port
        self._process = process

    def run(self):
        import urllib.request

        health_url = f"http://127.0.0.1:{self._port}/health"
        for _attempt in range(30):
            time.sleep(1)
            if self._process.poll() is not None:
                self.failure.emit(
                    f"Server exited with code {self._process.returncode}"
                )
                return
            try:
                resp = urllib.request.urlopen(health_url, timeout=2)
                if resp.status == 200:
                    self.success.emit(self._port)
                    return
            except Exception:
                pass
        self.failure.emit("Server did not become healthy within 30s")


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

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._process: subprocess.Popen | None = None
        self._stdout_reader: _ServerLogReader | None = None
        self._stderr_reader: _ServerLogReader | None = None
        self._health_worker: _HealthWorker | None = None
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
        # Pre-validate numeric arguments before any side effects
        if not (1024 <= port <= 65535):
            self.server_error.emit(f"Port must be 1024-65535, got {port}")
            return False
        if ctx_size < 256:
            self.server_error.emit(f"context size must be >= 256, got {ctx_size}")
            return False

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
        ngl_val = "auto" if n_gpu_layers in (99, -1) else str(n_gpu_layers)
        cmd = [
            binary,
            "--model", model_path,
            "--port", str(port),
            "-c", str(ctx_size),
            "-ngl", ngl_val,
        ]
        if threads > 0:
            cmd.extend(["--threads", str(threads)])

        # Append memory configurations if settings are available
        if self._settings:
            if self._settings.get_bool("server/flash_attn"):
                cmd.extend(["--flash-attn", "on"])
            if not self._settings.get_bool("server/mmap"):
                cmd.append("--no-mmap")
            if self._settings.get_bool("server/mlock"):
                cmd.append("--mlock")
            
            batch_size = self._settings.get_int("server/batch_size")
            if batch_size > 0:
                cmd.extend(["--batch-size", str(batch_size)])
            
            ubatch_size = self._settings.get_int("server/ubatch_size")
            if ubatch_size > 0:
                cmd.extend(["--ubatch-size", str(ubatch_size)])
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
        # Health-check in a background thread (non-blocking for the UI)
        self._health_worker = _HealthWorker(port, self._process, self)
        self._health_worker.success.connect(self._on_health_success)
        self._health_worker.failure.connect(self._on_health_failure)
        self._health_worker.start()
        return True

    def _on_health_success(self, port: int):
        """Called when the health-check worker confirms the server is up."""
        self._health_worker = None
        self.server_started.emit(port)

    def _on_health_failure(self, msg: str):
        """Called when the health-check worker gives up."""
        self._health_worker = None
        self.server_error.emit(msg)
        # Kill the orphaned process if still alive
        if self._process and self._process.poll() is None:
            try:
                self._process.kill()
                self._process.wait(timeout=3)
            except Exception:
                pass
        self._cleanup()

    @Slot(result=bool)
    def stop(self) -> bool:
        """Stop the server with SIGTERM → wait 5s → SIGKILL.

        Always releases resources (log readers, health worker, pipes) even
        if the process is already gone — this prevents lingering threads.
        """
        if self.is_running():
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
    @Slot(result='QVariant')
    def get_process(self):
        """Return the current server process (or None)."""
        return self._process

    def _cleanup(self):
        """Clean up log readers and process reference."""
        # Close pipes to unblock any reader thread stuck on readline()
        if self._process:
            try:
                if self._process.stdout:
                    self._process.stdout.close()
            except Exception:
                pass
            try:
                if self._process.stderr:
                    self._process.stderr.close()
            except Exception:
                pass
        if self._stdout_reader:
            self._stdout_reader.stop()
            self._stdout_reader.wait(2000)
            self._stdout_reader = None
        if self._stderr_reader:
            self._stderr_reader.stop()
            self._stderr_reader.wait(2000)
            self._stderr_reader = None
        if self._health_worker:
            self._health_worker.terminate()
            self._health_worker = None
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

            self.log_line.emit(f"Port {port} is occupied, killing existing process...")
            import subprocess
            # Find PID using the port. fuser is part of psmisc on most
            # distros; we degrade gracefully if it isn't available.
            try:
                out = subprocess.run(
                    ["fuser", str(port) + "/tcp"],
                    capture_output=True, text=True, timeout=5,
                )
            except FileNotFoundError:
                self.log_line.emit(
                    "fuser not found; cannot identify port owner. "
                    "Install psmisc or free the port manually."
                )
                return
            import os
            for pid_str in out.stdout.split():
                try:
                    pid = int(pid_str)
                except ValueError:
                    self.log_line.emit(
                        f"Skipping non-numeric PID from fuser: {pid_str!r}"
                    )
                    continue
                self.log_line.emit(f"Killing PID {pid} on port {port}")
                try:
                    os.kill(pid, 15)  # SIGTERM
                except ProcessLookupError:
                    continue  # already gone
                except PermissionError:
                    self.log_line.emit(
                        f"PID {pid} not owned by us; cannot kill (need sudo)."
                    )
                    continue
                time.sleep(1)
                # Verify still alive; only then escalate to SIGKILL
                try:
                    os.kill(pid, 0)
                    try:
                        os.kill(pid, 9)  # SIGKILL
                    except PermissionError:
                        self.log_line.emit(
                            f"PID {pid} not owned by us; cannot force-kill."
                        )
                except ProcessLookupError:
                    pass  # died from SIGTERM — fine
                except PermissionError:
                    # Process exists but became owned-by-other-user; skip.
                    pass
            # If fuser returned no usable PIDs, surface why it gave up
            if not out.stdout.strip() and out.returncode != 0:
                # 1 = nothing matched, non-1 = looked but failed (often
                # permission); fuser writes its diagnostics to stderr
                self.log_line.emit(
                    f"fuser could not identify owner of port {port}: "
                    f"{(out.stderr or '').strip() or 'unknown error'}"
                )
            time.sleep(1)
        except Exception as e:
            self.log_line.emit(f"Port cleanup warning: {e}")
