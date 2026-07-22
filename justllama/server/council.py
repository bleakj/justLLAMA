"""Council Mode Orchestration — sequentially queries three models and synthesizes responses."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot, Property

from justllama.server.client import LlamaClient
from justllama.server.providers import get_provider, provider_base_url, PROVIDER_IDS


class CouncilRunner(QThread):
    """Worker thread that sequentializes stopping, starting, and querying models."""

    progress_update = Signal(str)
    synthesis_ready = Signal(str)
    error = Signal(str)

    def __init__(self, prompt: str, settings, server_manager, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.settings = settings
        self.server_manager = server_manager
        self._stop_requested = False

    def stop(self):
        """Request the running council run to abort (best-effort)."""
        self._stop_requested = True
        self.requestInterruption()

    def run(self):
        try:
            self._execute()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

    def _execute(self):
        models = [
            self.settings.get_string("council/model_1"),
            self.settings.get_string("council/model_2"),
            self.settings.get_string("council/model_3")
        ]
        
        main_model = self.settings.get_string("server/model_path")
        binary = self.settings.get_string("server/binary")
        port = self.settings.get_int("server/port") or 8080
        # ctx_size and n_gpu_layers may be "auto" or 0 for auto-detection
        ctx_size = self.settings.get_int("server/ctx_size") or 0
        # n_gpu_layers can be "auto" (string) or an integer
        n_gpu_raw = self.settings.get_string("server/n_gpu_layers")
        try:
            n_gpu_layers = int(n_gpu_raw)
        except (ValueError, TypeError):
            n_gpu_layers = "auto"
        threads = self.settings.get_int("server/threads")

        responses = []
        client = LlamaClient(port=port)
        local_server_stopped = False

        for i, model_path in enumerate(models, start=1):
            if not model_path:
                self.progress_update.emit(f"Council Model {i} is not configured. Skipping.")
                responses.append(f"Model {i} not configured.")
                continue

            # Intercept cloud API models
            if model_path.startswith(tuple(f"{p}:" for p in PROVIDER_IDS)):
                try:
                    provider, actual_model = model_path.split(":", 1)
                    api_key = self.settings.get_api_key(provider)
                    if not api_key:
                        self.progress_update.emit(f"API key for {provider} not configured. Skipping Council Model {i}.")
                        responses.append(f"Model {i} (cloud {provider}) missing API key.")
                        continue
                    
                    self.progress_update.emit(f"Querying Council Model {i}/3 ({provider}): {actual_model}...")
                    
                    host = provider_base_url(provider, self.settings)
                    prov = get_provider(provider)
                    cloud_client = LlamaClient(host=host, port=None, api_key=api_key, api_prefix=prov.api_prefix)
                    resp = cloud_client.chat_completion(
                        messages=[{"role": "user", "content": self.prompt}],
                        model=actual_model,
                        temperature=0.7,
                        max_tokens=1024,
                        stream=False
                    )
                    answer = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not answer:
                        answer = "No response content received from cloud provider."
                    responses.append(answer)
                except Exception as e:
                    self.progress_update.emit(f"Error querying cloud model {model_path}: {e}. Skipping.")
                    responses.append(f"Model {i} query error: {e}")
                continue

            model_name = Path(model_path).name
            self.progress_update.emit(f"Loading Council Model {i}/3: {model_name}...")

            # Stop existing server
            if self.server_manager.is_running():
                self.server_manager.stop()
                local_server_stopped = True
                time.sleep(1)  # Release TCP socket port buffer
            # Start server with target council model
            ok = self.server_manager.start(binary, model_path, port)
            local_server_stopped = True
            if not ok:
                self.progress_update.emit(f"Failed to start Council Model {i}. Skipping.")
                responses.append(f"Model {i} failed to start.")
                continue

            # Wait for healthy server state
            healthy = self._wait_for_health(port)
            if not healthy:
                self.progress_update.emit(f"Council Model {i} did not become healthy. Skipping.")
                responses.append(f"Model {i} failed health check.")
                continue

            self.progress_update.emit(f"Querying Council Model {i}/3: {model_name}...")
            
            try:
                resp = client.chat_completion(
                    messages=[{"role": "user", "content": self.prompt}],
                    temperature=0.7,
                    max_tokens=1024,
                    stream=False
                )
                answer = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not answer:
                    answer = "No response content received."
                responses.append(answer)
            except Exception as e:
                self.progress_update.emit(f"Error querying Council Model {i}: {e}. Skipping.")
                responses.append(f"Model {i} query error: {e}")

        # Stop the last council model server
        if local_server_stopped and self.server_manager.is_running():
            self.server_manager.stop()
            time.sleep(1)
        # 2. Build synthesis prompt — only call the synthesis step when at
        # least one of the council models returned a real answer. Sending a
        # synthesis prompt with placeholder/error text for ALL three slots
        # would just produce a confused response from the synthesizer.
        real_responses = [
            r for r in responses
            if r and not r.startswith(
                ("Model ", "Council Model ")  # our "not configured" / "failed" placeholders
            )
            and not r.startswith("No response content received.")
        ]
        if not real_responses:
            self.error.emit(
                "No council model produced a response. "
                "Configure council/model_1, 2, 3 in settings."
            )
            return

        synthesis_prompt = (
            f"Here is a user's original query, along with plans/answers proposed by three different models "
            f"in a council. Evaluate all of them, compare their strengths and weaknesses, "
            f"and produce a final unified, best plan/response.\n\n"
            f"### Original Query:\n{self.prompt}\n\n"
            f"### Council Model 1 Response:\n{responses[0]}\n\n"
            f"### Council Model 2 Response:\n{responses[1]}\n\n"
            f"### Council Model 3 Response:\n{responses[2]}\n\n"
            f"Based on the above inputs, synthesize the final, comprehensive plan/answer."
        )

        # 3. Restore the main model
        if local_server_stopped and main_model:
            main_name = Path(main_model).name
            self.progress_update.emit(f"Restoring main model: {main_name}...")
            ok = self.server_manager.start(binary, main_model, port)
            if ok:
                healthy = self._wait_for_health(port)
        self.progress_update.emit("Council queries complete. Synthesizing final response...")
        if not self._stop_requested:
            self.synthesis_ready.emit(synthesis_prompt)

    def _wait_for_health(self, port: int) -> bool:
        health_url = f"http://127.0.0.1:{port}/health"
        for _ in range(30):
            time.sleep(1)
            proc = self.server_manager.get_process()
            if proc and proc.poll() is not None:
                return False
            try:
                resp = urllib.request.urlopen(health_url, timeout=2)
                if resp.status == 200:
                    return True
            except Exception:
                pass
        return False


class CouncilManager(QObject):
    """Manager exposed to QML to trigger and track council runs."""

    progress_update = Signal(str)
    synthesis_ready = Signal(str)
    error = Signal(str)
    models_changed = Signal()

    def __init__(self, settings, server_manager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.server_manager = server_manager
        self._runner = None
        # Update UI when settings change
        self.settings.settings_changed.connect(self._on_settings_changed)

    def _on_settings_changed(self, key, value):
        if key in ("server/model_path", "council/model_1", "council/model_2", "council/model_3"):
            self.models_changed.emit()

    @Property(list, notify=models_changed)
    def active_models(self) -> list:
        res = []
        # Main synthesizer model
        main_model = self.settings.get_string("server/model_path")
        if main_model:
            res.append(f"Synthesizer: {Path(main_model).name}")
        else:
            res.append("Synthesizer: None loaded")
        # Council models
        for i in range(1, 4):
            m = self.settings.get_string(f"council/model_{i}")
            if m:
                res.append(f"Model {i}: {Path(m).name}")
            else:
                res.append(f"Model {i}: (Not Configured)")
        return res
    @Slot()
    def stop(self):
        """Request the running council run to stop and wait for it."""
        if self._runner is not None and self._runner.isRunning():
            self._runner.stop()
            self._runner.wait()
        self._runner = None

    @Slot(str)
    def start_council(self, prompt: str):
        """Start the background runner thread."""
        # Gracefully stop any in-flight run instead of hard-terminating the
        # thread. QThread.terminate() can kill the worker mid server-swap and
        # leave llama-server in an inconsistent (half-restarted) state.
        self.stop()

        self._runner = CouncilRunner(prompt, self.settings, self.server_manager, self)
        self._runner.progress_update.connect(self.progress_update.emit)
        self._runner.synthesis_ready.connect(self.synthesis_ready.emit)
        self._runner.error.connect(self.error.emit)
        self._runner.start()
