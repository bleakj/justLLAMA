"""Shared ComfyUI subprocess and API helpers for image and video generation."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path


# ── constants ──────────────────────────────────────────────────────────────

COMFYUI_DIR = Path.home() / ".config" / "comfy-cli" / "ComfyUI"
PORT = 8188
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
PROMPT_URL = f"http://127.0.0.1:{PORT}/prompt"
COMFYUI_OUTPUT = COMFYUI_DIR / "output"


# ── lifecycle helpers ──────────────────────────────────────────────────────

def wait_for_comfy_health(comfy_proc: subprocess.Popen, timeout: int) -> bool:
    """Poll ComfyUI health endpoint until it responds or timeout."""
    for _ in range(timeout):
        if comfy_proc.poll() is not None:
            return False  # ComfyUI crashed
        try:
            resp = urllib.request.urlopen(HEALTH_URL, timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False
def wait_for_comfy_execution(comfy_proc: subprocess.Popen, prompt_id: str, timeout: int) -> dict | None:
    """Poll ComfyUI /history until the prompt_id finishes or timeout.

    On success returns the history entry dict (with ``outputs`` when the
    prompt produced files). On failure returns a dict tagged with
    ``"status": "error"`` carrying ComfyUI's error details (``status_str``,
    ``node_errors``, ``exception_message``) so callers can surface a
    diagnostic to the user or feed it back to an agent for autonomous
    troubleshooting.
    """
    history_url = f"http://127.0.0.1:{PORT}/history/{prompt_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if comfy_proc.poll() is not None:
            return None  # ComfyUI crashed
        try:
            resp = urllib.request.urlopen(history_url, timeout=5)
            data = json.loads(resp.read().decode())
            if prompt_id in data:
                entry = data[prompt_id]
                # A finished-but-failed run reports a non-null "status" payload.
                status = entry.get("status")
                if isinstance(status, dict) and status.get("status_str") == "error":
                    return {
                        "status": "error",
                        "status_str": "error",
                        "node_errors": status.get("messages", []),
                        "exception_message": _extract_exception(status.get("messages", [])),
                    }
                return entry
        except Exception:
            pass
        time.sleep(1)
    return None


def _extract_exception(messages: list) -> str:
    """Pull the human-readable exception text out of ComfyUI's status messages."""
    for msg in messages:
        # Messages are [["data", ...], "text"] tuples; the text often contains
        # the exception type + message.
        if isinstance(msg, (list, tuple)) and len(msg) >= 2 and isinstance(msg[-1], str):
            text = msg[-1]
            if "Error" in text or "Exception" in text:
                return text
    return ""


def launch_comfyui() -> subprocess.Popen | None:
    """Start ComfyUI as a subprocess. Returns Popen or None on failure."""
    main_py = COMFYUI_DIR / "main.py"
    if not main_py.is_file():
        print(f"ComfyUI not found at {main_py}")
        return None
    try:
        proc = subprocess.Popen(
            ["python3", "main.py", "--listen", "127.0.0.1", "--port", str(PORT)],
            cwd=str(COMFYUI_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except OSError as e:
        print(f"Failed to launch ComfyUI: {e}")
        return None


def stop_comfyui(proc: subprocess.Popen | None):
    """SIGTERM → 5s → SIGKILL."""
    if proc is None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    except (ProcessLookupError, OSError):
        pass


def find_latest_output(prefix: str, ext: str = "png") -> str | None:
    """Find the most recently created file in ComfyUI output matching prefix + ext."""
    candidates = sorted(COMFYUI_OUTPUT.glob(f"{prefix}*.{ext}"), key=os.path.getmtime)
    return str(candidates[-1]) if candidates else None
