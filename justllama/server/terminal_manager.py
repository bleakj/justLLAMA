"""Persistent PTY shell process management for justLLAMA."""

import os
import subprocess
import threading
import queue
from PySide6.QtCore import QObject, Signal, Slot


class TerminalManager(QObject):
    """Manages a persistent, interactive bash shell session via a PTY.

    Allows both python skills and QML UI elements to read and write to the
    same active shell process.
    """

    data_received = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.process: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self._running = False
        self._history = ""
        self._history_lock = threading.Lock()

        self.queues: list[queue.Queue] = []
        self.queues_lock = threading.Lock()

    @Slot()
    def start_session(self) -> None:
        """Start the persistent shell session if it is not already running."""
        if self.process is not None:
            if self.process.poll() is None:
                return
            else:
                self.stop_session()

        try:
            self.master_fd, self.slave_fd = os.openpty()
        except AttributeError:
            # Fallback for platforms without openpty support
            print("[TerminalManager] os.openpty is not supported on this platform.")
            return
        except Exception as e:
            print(f"[TerminalManager] failed to open PTY: {e}")
            return

        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["PS1"] = "justllama-pty$ "

        try:
            self.process = subprocess.Popen(
                ["bash", "--norc", "--noprofile"],
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )
        except Exception as e:
            print(f"[TerminalManager] failed to spawn bash: {e}")
            os.close(self.slave_fd)
            os.close(self.master_fd)
            self.master_fd = None
            self.slave_fd = None
            return

        # Close slave file descriptor in the parent process
        os.close(self.slave_fd)
        self.slave_fd = None

        self._running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

        # Send initial newline to force prompt drawing
        self.send_keys("\n")

    def _read_loop(self) -> None:
        while self._running and self.master_fd is not None:
            try:
                data_bytes = os.read(self.master_fd, 4096)
                if not data_bytes:
                    break
                data = data_bytes.decode("utf-8", errors="replace")

                with self._history_lock:
                    self._history += data
                    if len(self._history) > 100000:
                        self._history = self._history[-100000:]

                with self.queues_lock:
                    for q in self.queues:
                        q.put(data)

                self.data_received.emit(data)
            except Exception:
                break

        # Session stopped or EOF reached
        self.stop_session()

    @Slot(str)
    def send_keys(self, text: str) -> None:
        """Write characters directly to the shell stdin PTY."""
        if self.process is None or self.process.poll() is not None:
            self.start_session()

        if self.master_fd is not None:
            try:
                os.write(self.master_fd, text.encode("utf-8"))
            except Exception as e:
                print(f"[TerminalManager] failed to write to PTY: {e}")

    @Slot(result=str)
    def get_history(self) -> str:
        """Return the accumulated stdout/stderr output from the current session."""
        with self._history_lock:
            return self._history

    @Slot()
    def stop_session(self) -> None:
        """Stop the bash subprocess and clean up file descriptors."""
        self._running = False
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

    def shutdown(self) -> None:
        """Application closing cleanup."""
        self.stop_session()

    def register_queue(self, q: queue.Queue) -> None:
        """Add a queue subscriber to receive incoming terminal output chunks."""
        with self.queues_lock:
            if q not in self.queues:
                self.queues.append(q)

    def unregister_queue(self, q: queue.Queue) -> None:
        """Remove a queue subscriber."""
        with self.queues_lock:
            if q in self.queues:
                self.queues.remove(q)


# Module-level singleton
terminal_manager = TerminalManager()
