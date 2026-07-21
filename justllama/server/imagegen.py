"""Image Generation — ComfyUI subprocess lifecycle and prompt execution."""

from __future__ import annotations

import json
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
_MODELS_DIR = Path.home() / "Documents" / "models" / "image"
_WORKFLOW_FILE = Path(__file__).parent / "flux_workflow.json"
_LAUNCH_TIMEOUT = 60          # seconds to wait for ComfyUI to become healthy
_GENERATION_TIMEOUT = 120     # seconds to wait for image generation


# ── helpers ────────────────────────────────────────────────────────────────

def _scan_models() -> list[dict]:
    """List available GGUF image models in the models directory."""
    models = []
    if not _MODELS_DIR.is_dir():
        return models
    for f in sorted(_MODELS_DIR.rglob("*.gguf")):
        stat = f.stat()
        rel_path = f.relative_to(_MODELS_DIR)
        name = str(rel_path.parent / rel_path.stem) if rel_path.parent.name else rel_path.stem
        if name.endswith(".gguf"):
            name = name[:-5]
        models.append({
            "name": name,
            "path": str(f),
            "size_bytes": stat.st_size,
        })
    return models




# ── worker thread ──────────────────────────────────────────────────────────

class ImageGenRunner(QThread):
    """Background thread for ComfyUI lifecycle and image generation."""

    progress_update = Signal(str)
    generation_complete = Signal(str)   # file path of generated PNG
    error = Signal(str)                 # error message

    def __init__(self, prompt: str, workflow_template: dict,
                 model_name: str, server_manager, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.workflow_template = workflow_template
        self.model_name = model_name
        self.server_manager = server_manager
        self._stop_requested = False

    def stop(self):
        """Request the running generation to abort (best-effort)."""
        self._stop_requested = True
        self.requestInterruption()

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self.error.emit(f"Image generation failed: {e}")

    # ── internal lifecycle ─────────────────────────────────────────────

    def _execute(self):
        # 1. Stop llama-server to free VRAM
        was_running = self.server_manager.is_running()
        if was_running:
            self.progress_update.emit("Stopping language model server...")
            self.server_manager.stop()
            time.sleep(1)  # port release buffer

        # 2. Launch ComfyUI
        self.progress_update.emit("Starting image generation engine...")
        comfy_proc = launch_comfyui()
        if comfy_proc is None:
            self.error.emit("Failed to start image generation backend")
            self._restore_server(was_running)
            return

        # 3. Wait for healthy
        self.progress_update.emit("Waiting for image engine...")
        if not wait_for_comfy_health(comfy_proc, _LAUNCH_TIMEOUT):
            self.error.emit("Image generation engine did not start within 60s")
        image_path = self._post_prompt(comfy_proc)
        if image_path and not self._stop_requested:
            self.generation_complete.emit(image_path)
        elif not self._stop_requested:
            self.error.emit("Image generation did not produce an output file")

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

    # ── image generation ───────────────────────────────────────────────

    def _post_prompt(self, comfy_proc: subprocess.Popen) -> str | None:
        """POST the workflow to ComfyUI and wait for the output image."""
        # Build the workflow payload
        workflow = json.loads(json.dumps(self.workflow_template))  # deep copy

        # Patch the prompt into the workflow (search PROMPT_PLACEHOLDER in any node)
        self._patch_prompt(workflow, self.prompt)

        # Patch the model name into UNET loader nodes
        self._patch_model(workflow, self.model_name)

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
            # ComfyUI may return a different prompt_id; use what it gives back
            effective_id = result.get("prompt_id", prompt_id)
        except Exception as e:
            self.error.emit(f"Failed to submit prompt: {e}")
            return None

        # Wait for completion
        history = wait_for_comfy_execution(comfy_proc, effective_id, _GENERATION_TIMEOUT)
        if history is None:
            self.error.emit("Image generation timed out")
            return None
        if history.get("status") == "error":
            self.error.emit(
                "Image generation failed: "
                + (history.get("exception_message") or "unknown ComfyUI error")
            )
            return None

        # Find the output file
        # SaveImage node outputs are under history["outputs"][node_id]["images"]
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

        # Fallback: scan for latest justllama_*.png
        return find_latest_output("justllama_")

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
        """Replace MODEL_PLACEHOLDER in UNET loader inputs with the selected model filename."""
        for node in workflow.values():
            if isinstance(node, dict):
                if node.get("class_type", "").endswith("LoaderGGUF"):
                    inputs = node.get("inputs", {})
                    for key, val in inputs.items():
                        if isinstance(val, str) and "unet_name" in key.lower():
                            inputs[key] = model_name
                        elif isinstance(val, str) and val == "MODEL_PLACEHOLDER":
                            inputs[key] = model_name


# ── QML-exposed manager ────────────────────────────────────────────────────

class ImageGenManager(QObject):
    """Manages image generation — exposed to QML as imageGenManager.

    Usage in QML:

        ImageGenView {
            // ...
            Button {
                text: "Generate"
                onClicked: imageGenManager.generate(promptField.text)
            }
        }

        Connections {
            target: imageGenManager
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
        self._runner: ImageGenRunner | None = None
        self._workflow_template: dict | None = None
        self._last_output: str | None = None
        self._last_error: str | None = None
        self._load_workflow()

    # ── public API ────────────────────────────────────────────────────

    @Slot(str)
    def generate(self, prompt: str):
        """Start image generation in a background thread.

        Does NOT block — connect to ``generation_complete`` and ``error``
        signals for the result.
        """
        if self._runner and self._runner.isRunning():
            self.error.emit("Already generating an image — wait for completion")
            return

        if not prompt.strip():
            self.error.emit("Prompt cannot be empty")
            return

        if self._workflow_template is None:
            self.error.emit("Workflow template not loaded — check flux_workflow.json")
            return

        selected = self._selected_model_path()
        if not selected:
            self.error.emit("No image model selected")
            return

        model_name = Path(selected).name

        self._runner = ImageGenRunner(
            prompt.strip(), self._workflow_template,
            model_name, self.server_manager, self
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
        """Return list of discovered GGUF image models."""
        return _scan_models()

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

    @Slot(str)
    def generate_from_workflow(self, workflow_json: str):
        """Run image generation from a raw ComfyUI API-format workflow JSON.

        Unlike :meth:`generate` (which patches the static ``flux_workflow.json``
        template), this accepts a complete workflow authored by the agent /
        LLM. ``PROMPT_PLACEHOLDER`` / ``MODEL_PLACEHOLDER`` are still patched if
        present, so a partially-templated workflow works too.

        Returns nothing — connect to ``generation_complete`` / ``error`` signals.
        """
        if self._runner and self._runner.isRunning():
            self.error.emit("Already generating an image — wait for completion")
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
            self.error.emit("No image model selected")
            return
        model_name = Path(selected).name

        self._runner = ImageGenRunner(
            "", workflow,
            model_name, self.server_manager, self
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
        """Persist the selected image model path."""
        from justllama.config.settings import AppSettings
        AppSettings().set_string("imagegen/model_path", path)

    @Slot(result=str)
    def selected_model(self) -> str:
        """Return the currently selected image model path or empty string."""
        from justllama.config.settings import AppSettings
        return AppSettings().get_string("imagegen/model_path")

    # ── internal helpers ──────────────────────────────────────────────

    def _load_workflow(self):
        """Load the workflow template from flux_workflow.json."""
        if _WORKFLOW_FILE.is_file():
            try:
                self._workflow_template = json.loads(_WORKFLOW_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"ImageGen: failed to load workflow template: {e}")
        else:
            print("ImageGen: flux_workflow.json not found — workflow template unavailable")

    def _selected_model_path(self) -> str:
        """Get the selected model path, or empty string."""
        from justllama.config.settings import AppSettings
        return AppSettings().get_string("imagegen/model_path")
