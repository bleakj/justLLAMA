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

def wait_for_comfy_health(timeout: int) -> bool:
    """Poll ComfyUI health endpoint until it responds or timeout."""
    for _ in range(timeout):
        try:
            resp = urllib.request.urlopen(HEALTH_URL, timeout=2)
            if resp.status == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_comfy_execution(prompt_id: str, timeout: int) -> dict | None:
    """Poll ComfyUI /history until the prompt_id finishes or timeout."""
    history_url = f"http://127.0.0.1:{PORT}/history/{prompt_id}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(history_url, timeout=5)
            data = json.loads(resp.read().decode())
            if prompt_id in data:
                return data[prompt_id]
        except Exception:
            pass
        time.sleep(1)
    return None


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
