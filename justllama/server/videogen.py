"""Video Generation — ComfyUI subprocess lifecycle and prompt execution."""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
import uuid
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot

from justllama.server.comfy_helpers import (
    COMFYUI_DIR, PROMPT_URL,
    wait_for_comfy_health, wait_for_comfy_execution,
    launch_comfyui, stop_comfyui, find_latest_output,
)

# ── constants ──────────────────────────────────────────────────────────────

_VIDEO_MODELS_DIR = Path.home() / "Documents" / "models" / "video"
_VIDEO_LAUNCH_TIMEOUT = 60
_VIDEO_GENERATION_TIMEOUT = 300   # 5 minutes for video

_WORKFLOW_MAP: dict[str, str] = {
    "ltx": "ltx_workflow.json",
}
_WORKFLOW_DIR = Path(__file__).parent


# ── architecture detection ─────────────────────────────────────────────────

def _detect_architecture(model_name: str) -> str:
    """Detect video architecture from model filename stem.

    Returns one of the keys in _WORKFLOW_MAP.
    """
    stem = Path(model_name).stem.lower()
    for prefix in _WORKFLOW_MAP:
        if stem.startswith(prefix):
            return prefix
    # Default to WAN (catch-all for wan22, scail, lance, sulphur, etc.)
    return "wan"


# ── model discovery ────────────────────────────────────────────────────────

def _scan_video_models() -> list[dict]:
    """List available GGUF video models in the video models directory."""
    models: list[dict] = []
    if not _VIDEO_MODELS_DIR.is_dir():
        return models
    for f in sorted(_VIDEO_MODELS_DIR.glob("*.gguf")):
        stat = f.stat()
        arch = _detect_architecture(f.stem)
        badge = "[LTX]" if arch == "ltx" else "[WAN]"
        models.append({
            "name": f"{badge} {f.stem}",
            "path": str(f),
            "size_bytes": stat.st_size,
        })
    return models


# ── worker thread ──────────────────────────────────────────────────────────

class VideoGenRunner(QThread):
    """Background thread for ComfyUI lifecycle and video generation."""

    progress_update = Signal(str)
    generation_complete = Signal(str)   # file path of generated video
    error = Signal(str)                 # error message

    def __init__(self, prompt: str, workflow_template: dict,
                 model_name: str, server_manager,
                 width: int = 832, height: int = 480, length: int = 49,
                 parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.workflow_template = workflow_template
        self.model_name = model_name
        self.server_manager = server_manager
        self.width = width
        self.height = height
        self.length = length
        self._stop_requested = False

    def stop(self):
        """Request the running generation to abort (best-effort)."""
        self._stop_requested = True
        self.requestInterruption()

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.error.emit(f"Video generation failed: {e}")

    # ── internal lifecycle ─────────────────────────────────────────────

    def _execute(self):
        # 1. Stop llama-server to free VRAM
        was_running = self.server_manager.is_running()
        if was_running:
            self.progress_update.emit("Stopping language model server...")
            self.server_manager.stop()
            time.sleep(1)  # port release buffer

        # 2. Launch ComfyUI
        self.progress_update.emit("Starting video generation engine...")
        comfy_proc = launch_comfyui()
        if comfy_proc is None:
            self.error.emit("Failed to start video generation backend")
            self._restore_server(was_running)
            return

        # 3. Wait for healthy
        self.progress_update.emit("Waiting for video engine...")
        if not wait_for_comfy_health(comfy_proc, _VIDEO_LAUNCH_TIMEOUT):
            self.error.emit("Video generation engine did not start within 60s")
            stop_comfyui(comfy_proc)
            self._restore_server(was_running)
        video_path = self._post_prompt(comfy_proc)
        if video_path and not self._stop_requested:
            self.generation_complete.emit(video_path)
        elif not self._stop_requested:
            self.error.emit("Video generation did not produce an output file")

        # 5. Stop ComfyUI
        stop_comfyui(comfy_proc)

        # 6. Restart llama-server
        self._restore_server(was_running)

    def _restore_server(self, was_running: bool):
        """Restart llama-server if it was running before we stopped it."""
        if not was_running:
            return

        from justllama.config.settings import AppSettings
        settings = AppSettings()
        binary = settings.get_string("server/binary")
        model = settings.get_string("server/model_path")
        port = settings.get_int("server/port")
        ctx = settings.get_int("server/ctx_size")
        gpu = settings.get_int("server/n_gpu_layers")
        threads = settings.get_int("server/threads")

        if not model:
            self.progress_update.emit("No main model configured — cannot restore server")
            return

        self.progress_update.emit("Restoring language model server...")
        ok = self.server_manager.start(binary, model, port, ctx, gpu, threads)
        if not ok:
            self.error.emit("Failed to restore language model server")
            self.progress_update.emit("ERROR: failed to restore server")

    # ── video generation ───────────────────────────────────────────────

    def _post_prompt(self, comfy_proc) -> str | None:
        """POST the workflow to ComfyUI and wait for the output video."""
        # Build the workflow payload
        workflow = json.loads(json.dumps(self.workflow_template))  # deep copy

        # Patch the prompt into the workflow
        self._patch_prompt(workflow, self.prompt)

        # Patch the model name into UNET loader nodes
        self._patch_model(workflow, self.model_name)

        # Patch width, height, length
        self._patch_dimensions(workflow)

        # Patch seed
        self._patch_seed(workflow)

        prompt_id = str(uuid.uuid4())
        payload = {
            "prompt": workflow,
            "client_id": "justllama",
            "prompt_id": prompt_id,
        }

        try:
            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                PROMPT_URL, data=body,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            effective_id = result.get("prompt_id", prompt_id)
        except Exception as e:
            self.error.emit(f"Failed to submit prompt: {e}")
            return None

        # Wait for completion (longer timeout for video)
        history = wait_for_comfy_execution(comfy_proc, effective_id, _VIDEO_GENERATION_TIMEOUT)
        if history is None:
            self.error.emit("Video generation timed out after 5 minutes")
            return None
        if history.get("status") == "error":
            self.error.emit(
                "Video generation failed: "
                + (history.get("exception_message") or "unknown ComfyUI error")
            )
            return None

        # Find the output file — webp or mp4
        outputs = history.get("outputs", {})
        for node_id, node_out in outputs.items():
            images = node_out.get("images", [])
            for img in images:
                if img.get("type") == "output":
                    filename = img.get("filename", "")
                    subfolder = img.get("subfolder", "")
                    full_path = COMFYUI_DIR / "output" / subfolder / filename
                    if full_path.is_file():
                        return str(full_path.resolve())

        # Fallback: scan for latest justllama_video_*.webp
        path = find_latest_output("justllama_video_", "webp")
        if path:
            return path
        # Try mp4 fallback
        return find_latest_output("justllama_video_", "mp4")

    @staticmethod
    def _patch_prompt(workflow: dict, prompt: str):
        """Replace PROMPT_PLACEHOLDER in any node input."""
        for node in workflow.values():
            if isinstance(node, dict):
                inputs = node.get("inputs", {})
                for key, val in inputs.items():
                    if isinstance(val, str) and val == "PROMPT_PLACEHOLDER":
                        inputs[key] = prompt

    @staticmethod
    def _patch_model(workflow: dict, model_name: str):
        """Replace MODEL_PLACEHOLDER in UNET loader inputs."""
        for node in workflow.values():
            if isinstance(node, dict):
                if node.get("class_type", "").endswith("LoaderGGUF"):
                    inputs = node.get("inputs", {})
                    for key, val in inputs.items():
                        if isinstance(val, str) and "unet_name" in key.lower():
                            inputs[key] = model_name
                        elif isinstance(val, str) and val == "MODEL_PLACEHOLDER":
                            inputs[key] = model_name

    def _patch_dimensions(self, workflow: dict):
        """Replace WIDTH/HEIGHT/LENGTH placeholders with the configured values."""
        for node in workflow.values():
            if isinstance(node, dict):
                inputs = node.get("inputs", {})
                for key, val in inputs.items():
                    if isinstance(val, str) and val == "WIDTH_PLACEHOLDER":
                        inputs[key] = self.width
                    elif isinstance(val, str) and val == "HEIGHT_PLACEHOLDER":
                        inputs[key] = self.height
                    elif isinstance(val, str) and val == "LENGTH_PLACEHOLDER":
                        inputs[key] = self.length

    @staticmethod
    def _patch_seed(workflow: dict):
        """Replace noise_seed 0 with a time-based seed for reproducibility."""
        for node in workflow.values():
            if isinstance(node, dict):
                cls_type = node.get("class_type", "")
                if "Noise" in cls_type:
                    inputs = node.get("inputs", {})
                    for key, val in inputs.items():
                        if isinstance(val, (int, float)) and val == 0 and "seed" in key.lower():
                            inputs[key] = int(time.time() * 1000) % (2**32)


# ── QML-exposed manager ────────────────────────────────────────────────────

class VideoGenManager(QObject):
    """Manages video generation — exposed to QML as videoGenManager.

    Usage in QML:

        VideoGenView {
            // ...
            Button {
                text: "Generate"
                onClicked: videoGenManager.generate(promptField.text, 832, 480, 49)
            }
        }

        Connections {
            target: videoGenManager
            function onProgress_update(msg) { statusText.text = msg }
            function onGeneration_complete(path) { preview.source = "file://" + path }
            function onError(msg) { errorToast.show(msg) }
        }
    """

    progress_update = Signal(str)
    generation_complete = Signal(str)
    error = Signal(str)

    def __init__(self, server_manager, parent=None):
        super().__init__(parent)
        self.server_manager = server_manager
        self._runner: VideoGenRunner | None = None
        self._loaded_workflows: dict[str, dict] = {}
        self._last_output: str | None = None
        self._last_error: str | None = None

    # ── public API ────────────────────────────────────────────────────

    @Slot(str, int, int, int)
    def generate(self, prompt: str, width: int = 832, height: int = 480, length: int = 49):
        """Start video generation in a background thread.

        Does NOT block — connect to ``generation_complete`` and ``error``
        signals for the result.
        """
        if self._runner and self._runner.isRunning():
            self.error.emit("Already generating a video — wait for completion")
            return

        if not prompt.strip():
            self.error.emit("Prompt cannot be empty")
            return

        selected = self._selected_model_path()
        if not selected:
            self.error.emit("No video model selected")
            return

        model_name = Path(selected).name
        arch = _detect_architecture(model_name)
        workflow = self._get_workflow(arch)
        if workflow is None:
            self.error.emit(
                f"No workflow template available for architecture '{arch}' — "
                f"check {_WORKFLOW_DIR}/{'wan_workflow.json' if arch == 'wan' else f'{arch}_workflow.json'}"
            )
            return

        self._runner = VideoGenRunner(
            prompt.strip(), workflow,
            model_name, self.server_manager,
            width, height, length, self,
        )
        self._last_output = None
        self._last_error = None
        self._runner.progress_update.connect(self.progress_update.emit)
        self._runner.generation_complete.connect(self.generation_complete.emit)
        self._runner.generation_complete.connect(lambda p: setattr(self, "_last_output", p))
        self._runner.error.connect(self.error.emit)
        self._runner.error.connect(lambda m: setattr(self, "_last_error", m))
        self._runner.start()

    @Slot(result=list)
    def available_models(self) -> list[dict]:
        """Return list of discovered GGUF video models."""
        return _scan_video_models()

    @Slot(result=bool)
    def is_generating(self) -> bool:
        """Check if a generation thread is currently running."""
        return self._runner is not None and self._runner.isRunning()

    @Slot()
    def stop(self):
        """Request the running generation thread to stop and wait for it."""
        if self._runner is not None and self._runner.isRunning():
            self._runner.stop()
            self._runner.wait()

    @Slot(str, str)
    def copy_file(self, src: str, dest: str):
        """Copy a generated video file to a user-chosen destination (Save As)."""
        try:
            shutil.copy2(src, dest)
        except OSError as e:
            self.error.emit(f"Failed to save video: {e}")
    @Slot(str)
    def generate_from_workflow(self, workflow_json: str):
        """Run video generation from a raw ComfyUI API-format workflow JSON.

        Accepts a complete workflow authored by the agent / LLM. Model, prompt,
        and dimension placeholders are patched if present, so a partially
        templated workflow works too. Dimensions default to 832x480x49.

        Returns nothing — connect to ``generation_complete`` / ``error`` signals.
        """
        if self._runner and self._runner.isRunning():
            self.error.emit("Already generating a video — wait for completion")
            return

        try:
            workflow = json.loads(workflow_json)
        except (json.JSONDecodeError, TypeError) as e:
            self.error.emit(f"Invalid workflow JSON: {e}")
            return
        if not isinstance(workflow, dict) or not workflow:
            self.error.emit("Workflow JSON must be a non-empty object of nodes")
            return

        selected = self._selected_model_path()
        if not selected:
            self.error.emit("No video model selected")
            return
        model_name = Path(selected).name

        self._runner = VideoGenRunner(
            "", workflow,
            model_name, self.server_manager,
            832, 480, 49, self,
        )
        self._runner.progress_update.connect(self.progress_update.emit)
        self._runner.generation_complete.connect(self.generation_complete.emit)
        self._runner.generation_complete.connect(lambda p: setattr(self, "_last_output", p))
        self._runner.error.connect(self.error.emit)
        self._runner.error.connect(lambda m: setattr(self, "_last_error", m))
        self._runner.start()

    def wait_for_generation(self, cancel_check=None) -> tuple[str | None, str | None]:
        """Block until the current generation thread finishes.

        Returns ``(output_path, error_message)`` — exactly one is non-None.
        Intended for use from a blocking skill/tool call (the caller must be a
        different thread than the runner itself).
        """
        if self._runner is None:
            return None, "No generation has been started"
        self._runner.wait()
        return self._last_output, self._last_error
    @Slot(str)
    def select_model(self, path: str):
        """Persist the selected video model path."""
        from justllama.config.settings import AppSettings
        AppSettings().set_string("videogen/model_path", path)

    @Slot(result=str)
    def selected_model(self) -> str:
        """Return the currently selected video model path or empty string."""
        from justllama.config.settings import AppSettings
        return AppSettings().get_string("videogen/model_path")

    # ── internal helpers ──────────────────────────────────────────────

    def _get_workflow(self, arch: str) -> dict | None:
        """Load and cache a workflow template for the given architecture."""
        if arch in self._loaded_workflows:
            return self._loaded_workflows[arch]

        # For WAN (default catch-all), map to wan_workflow.json
        filename = _WORKFLOW_MAP.get(arch, "wan_workflow.json")
        wf_path = _WORKFLOW_DIR / filename
        if not wf_path.is_file():
            print(f"VideoGen: workflow file not found: {wf_path}")
            return None
        try:
            workflow = json.loads(wf_path.read_text(encoding="utf-8"))
            self._loaded_workflows[arch] = workflow
            return workflow
        except (json.JSONDecodeError, OSError) as e:
            print(f"VideoGen: failed to load workflow template '{filename}': {e}")
            return None

    def _selected_model_path(self) -> str:
        """Get the selected model path, or empty string."""
        from justllama.config.settings import AppSettings
        return AppSettings().get_string("videogen/model_path")
