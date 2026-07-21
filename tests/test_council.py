"""Unit tests for the Council Mode orchestrator and cloud model routing."""

from unittest.mock import MagicMock
from PySide6.QtCore import QSettings

from justllama.config.settings import AppSettings
from justllama.server.council import CouncilManager


def test_council_manager(qapp, tmp_path, monkeypatch):
    # Setup temp settings
    settings_file = str(tmp_path / "test_settings_council.conf")
    
    # Intercept QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    
    settings = AppSettings()
    settings.set_string("council/model_1", "model1.gguf")
    settings.set_string("council/model_2", "model2.gguf")
    settings.set_string("council/model_3", "model3.gguf")
    settings.set_string("server/model_path", "main_model.gguf")
    settings.set_string("server/binary", "llama-server")
    settings.set_int("server/port", 8080)
    
    # Mock ServerManager
    mock_server = MagicMock()
    mock_server.is_running.return_value = False
    mock_server.start.return_value = True
    mock_server._process = None
    
    # Mock LlamaClient chat_completion
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = [
        {"choices": [{"message": {"content": "Response 1"}}]},
        {"choices": [{"message": {"content": "Response 2"}}]},
        {"choices": [{"message": {"content": "Response 3"}}]}
    ]
    
    monkeypatch.setattr("justllama.server.council.LlamaClient", lambda port: mock_client)
    
    # Mock wait_for_health to always succeed
    monkeypatch.setattr(
        "justllama.server.council.CouncilRunner._wait_for_health",
        lambda self, port: True
    )

    # Mock QThread.start to be a no-op to run it synchronously
    monkeypatch.setattr("justllama.server.council.CouncilRunner.start", lambda self: None)
    
    manager = CouncilManager(settings, mock_server)
    
    # Capture signals
    progress_calls = []
    synthesis_prompt = []
    error_calls = []
    
    manager.progress_update.connect(progress_calls.append)
    manager.synthesis_ready.connect(synthesis_prompt.append)
    manager.error.connect(error_calls.append)
    
    # Start the council execution
    manager.start_council("What is 1+1?")
    
    # Manually execute the thread logic synchronously to avoid QThread scheduling issues
    manager._runner.run()
    
    # Verify results
    print("Progress calls:", progress_calls)
    print("Error calls:", error_calls)
    assert len(error_calls) == 0, f"Error occurred: {error_calls}"
    assert len(synthesis_prompt) == 1, "Synthesis not triggered"
    
    prompt = synthesis_prompt[0]
    assert "What is 1+1?" in prompt
    assert "Response 1" in prompt
    assert "Response 2" in prompt
    assert "Response 3" in prompt
    
    # Verify server starts (3 council models + 1 main model = 4 starts)
    assert mock_server.start.call_count == 4


def test_council_cloud_missing_keys(qapp, tmp_path, monkeypatch):
    # Setup temp settings
    settings_file = str(tmp_path / "test_settings_council_missing.conf")
    
    # Intercept QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    
    settings = AppSettings()
    # Configure all 3 models as cloud models
    settings.set_string("council/model_1", "nvidia:meta/llama-3")
    settings.set_string("council/model_2", "openrouter:google/gemini")
    settings.set_string("council/model_3", "opencode:qwen/qwen2")
    settings.set_string("server/model_path", "main_model.gguf")
    settings.set_string("server/binary", "llama-server")
    settings.set_int("server/port", 8080)
    
    # Ensure API keys are NOT set (empty environment)
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENCODE_API_KEY", "")
    
    # Mock ServerManager
    mock_server = MagicMock()
    mock_server.is_running.return_value = False
    mock_server.start.return_value = True
    
    # Mock LlamaClient (only local client will be instantiated at start)
    monkeypatch.setattr("justllama.server.council.LlamaClient", lambda *args, **kwargs: MagicMock())
    
    # Mock QThread.start to be a no-op
    monkeypatch.setattr("justllama.server.council.CouncilRunner.start", lambda self: None)
    
    manager = CouncilManager(settings, mock_server)
    
    # Capture signals
    progress_calls = []
    synthesis_prompt = []
    error_calls = []
    
    manager.progress_update.connect(progress_calls.append)
    manager.synthesis_ready.connect(synthesis_prompt.append)
    manager.error.connect(error_calls.append)
    
    # Start the council execution
    manager.start_council("What is 1+1?")
    manager._runner.run()
    
    # Verify results
    assert len(error_calls) == 1
    assert "No council model produced a response." in error_calls[0]
    assert len(synthesis_prompt) == 0
    
    progress_text = "".join(progress_calls)
    assert "API key for nvidia not configured" in progress_text
    assert "API key for openrouter not configured" in progress_text
    assert "API key for opencode not configured" in progress_text
    
    # Verify that the server manager was NOT started or stopped at all because they are cloud models
    assert mock_server.start.call_count == 0
    assert mock_server.stop.call_count == 0


def test_council_cloud_correct_keys(qapp, tmp_path, monkeypatch):
    # Setup temp settings
    settings_file = str(tmp_path / "test_settings_council_cloud.conf")
    
    # Intercept QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    
    settings = AppSettings()
    # Configure all 3 models as cloud models
    settings.set_string("council/model_1", "nvidia:meta/llama-3-nvidia")
    settings.set_string("council/model_2", "openrouter:google/gemini-openrouter")
    settings.set_string("council/model_3", "opencode:qwen/qwen2-opencode")
    settings.set_string("server/model_path", "main_model.gguf")
    settings.set_string("server/binary", "llama-server")
    settings.set_int("server/port", 8080)
    
    # Configure API keys via environment and custom opencode endpoint
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-secret-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret-key")
    monkeypatch.setenv("OPENCODE_API_KEY", "oc-secret-key")
    settings.set_string("cloud_endpoints/opencode", "https://custom-opencode.com/api")
    
    # Mock ServerManager
    mock_server = MagicMock()
    mock_server.is_running.return_value = False
    mock_server.start.return_value = True
    
    # Mock LlamaClient to capture construction and method calls
    client_calls = []
    class MockCloudLlamaClient:
        def __init__(self, host="http://localhost", port=8080, api_key=None, api_prefix=None):
            self.host = host
            self.port = port
            self.api_key = api_key
            client_calls.append(self)
            
        def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=1024, stream=False):
            self.completion_args = {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }
            return {"choices": [{"message": {"content": f"Response from {model} via {self.host}"}}]}
            
    monkeypatch.setattr("justllama.server.council.LlamaClient", MockCloudLlamaClient)
    
    # Mock QThread.start to be a no-op
    monkeypatch.setattr("justllama.server.council.CouncilRunner.start", lambda self: None)
    
    manager = CouncilManager(settings, mock_server)
    
    # Capture signals
    progress_calls = []
    synthesis_prompt = []
    error_calls = []
    
    manager.progress_update.connect(progress_calls.append)
    manager.synthesis_ready.connect(synthesis_prompt.append)
    manager.error.connect(error_calls.append)
    
    # Start the council execution
    manager.start_council("What is 1+1?")
    manager._runner.run()
    
    # Verify results
    assert len(error_calls) == 0
    assert len(synthesis_prompt) == 1
    prompt = synthesis_prompt[0]
    
    # Assert synthesis prompt contains the output from the cloud models
    assert "Response from meta/llama-3-nvidia via https://integrate.api.nvidia.com" in prompt
    assert "Response from google/gemini-openrouter via https://openrouter.ai/api" in prompt
    assert "Response from qwen/qwen2-opencode via https://custom-opencode.com/api" in prompt
    
    # Verify that LlamaClient was constructed 4 times (1 local at start, 3 cloud in loop)
    assert len(client_calls) == 4
    
    # Client 0: local client constructed at start of _execute
    assert client_calls[0].port == 8080
    assert client_calls[0].host == "http://localhost"
    
    # Client 1: nvidia
    assert client_calls[1].host == "https://integrate.api.nvidia.com"
    assert client_calls[1].port is None
    assert client_calls[1].api_key == "nv-secret-key"
    assert client_calls[1].completion_args["model"] == "meta/llama-3-nvidia"
    assert client_calls[1].completion_args["messages"] == [{"role": "user", "content": "What is 1+1?"}]
    
    # Client 2: openrouter
    assert client_calls[2].host == "https://openrouter.ai/api"
    assert client_calls[2].port is None
    assert client_calls[2].api_key == "or-secret-key"
    assert client_calls[2].completion_args["model"] == "google/gemini-openrouter"
    
    # Client 3: opencode
    assert client_calls[3].host == "https://custom-opencode.com/api"
    assert client_calls[3].port is None
    assert client_calls[3].api_key == "oc-secret-key"
    assert client_calls[3].completion_args["model"] == "qwen/qwen2-opencode"
    
    # Verify that the server manager was NOT started or stopped at all
    assert mock_server.start.call_count == 0
    assert mock_server.stop.call_count == 0


def test_council_mixed_config(qapp, tmp_path, monkeypatch):
    # Setup temp settings
    settings_file = str(tmp_path / "test_settings_council_mixed.conf")
    
    # Intercept QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    
    settings = AppSettings()
    # Model 1: local, Model 2: openrouter cloud, Model 3: nvidia cloud
    settings.set_string("council/model_1", "local_model1.gguf")
    settings.set_string("council/model_2", "openrouter:google/gemini-mixed")
    settings.set_string("council/model_3", "nvidia:meta/llama-3-mixed")
    settings.set_string("server/model_path", "main_model.gguf")
    settings.set_string("server/binary", "llama-server")
    settings.set_int("server/port", 8080)
    
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-mixed-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-mixed-key")
    
    # Use our stateful server manager mock
    class StatefulServerManagerMock:
        def __init__(self):
            self._running = False
            self.start_calls = []
            self.stop_calls = []
            self._process = None

        def is_running(self):
            return self._running

        def start(self, binary, model, port, ctx_size=4096, n_gpu_layers=99, threads=-1):
            self._running = True
            self.start_calls.append((binary, model, port, ctx_size, n_gpu_layers, threads))
            return True

        def stop(self):
            self._running = False
            self.stop_calls.append(True)

        def get_process(self):
            return self._process
            
    mock_server = StatefulServerManagerMock()
    
    # Mock LlamaClient to handle both local and cloud instantiations
    client_calls = []
    class MockMixedLlamaClient:
        def __init__(self, host="http://localhost", port=8080, api_key=None, api_prefix=None):
            self.host = host
            self.port = port
            self.api_key = api_key
            client_calls.append(self)
            
        def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=1024, stream=False):
            self.completion_args = {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }
            if self.port is not None:
                # Local client completion
                return {"choices": [{"message": {"content": "Response from Local Model"}}]}
            else:
                # Cloud client completion
                return {"choices": [{"message": {"content": f"Response from {model} via {self.host}"}}]}
                
    monkeypatch.setattr("justllama.server.council.LlamaClient", MockMixedLlamaClient)
    
    # Mock wait_for_health to always succeed
    monkeypatch.setattr(
        "justllama.server.council.CouncilRunner._wait_for_health",
        lambda self, port: True
    )
    
    # Mock QThread.start to be a no-op
    monkeypatch.setattr("justllama.server.council.CouncilRunner.start", lambda self: None)
    
    manager = CouncilManager(settings, mock_server)
    
    # Capture signals
    progress_calls = []
    synthesis_prompt = []
    error_calls = []
    
    manager.progress_update.connect(progress_calls.append)
    manager.synthesis_ready.connect(synthesis_prompt.append)
    manager.error.connect(error_calls.append)
    
    # Start the council execution
    manager.start_council("What is 1+1?")
    manager._runner.run()
    
    # Verify results
    assert len(error_calls) == 0
    assert len(synthesis_prompt) == 1
    prompt = synthesis_prompt[0]
    
    # Verify prompt contains both local and cloud responses
    assert "Response from Local Model" in prompt
    assert "Response from google/gemini-mixed via https://openrouter.ai/api" in prompt
    assert "Response from meta/llama-3-mixed via https://integrate.api.nvidia.com" in prompt
    
    # Verify LlamaClient construction:
    # 1. Local client created at start (port=8080)
    # 2. openrouter cloud client created (port=None)
    # 3. nvidia cloud client created (port=None)
    assert len(client_calls) == 3
    assert client_calls[0].port == 8080
    assert client_calls[1].host == "https://openrouter.ai/api"
    assert client_calls[1].port is None
    assert client_calls[2].host == "https://integrate.api.nvidia.com"
    assert client_calls[2].port is None
    
    # Verify server manager starts/stops:
    # - local_model1.gguf started
    # - main_model.gguf started to restore main model
    assert len(mock_server.start_calls) == 2
    assert mock_server.start_calls[0][1] == "local_model1.gguf"
    assert mock_server.start_calls[1][1] == "main_model.gguf"
    
    # Stop call should be called exactly once (to stop the local model server)
    assert len(mock_server.stop_calls) == 1


def test_council_cloud_partial_missing_keys(qapp, tmp_path, monkeypatch):
    # Setup temp settings
    settings_file = str(tmp_path / "test_settings_council_partial.conf")
    
    # Intercept QSettings constructor
    original_init = QSettings.__init__
    def _patched_init(self, *args, **kwargs):
        original_init(self, settings_file, QSettings.IniFormat)
    monkeypatch.setattr(QSettings, "__init__", _patched_init)
    
    settings = AppSettings()
    # Configure all 3 models as cloud models
    settings.set_string("council/model_1", "nvidia:meta/llama-3")
    settings.set_string("council/model_2", "openrouter:google/gemini")
    settings.set_string("council/model_3", "opencode:qwen/qwen2")
    settings.set_string("server/model_path", "main_model.gguf")
    settings.set_string("server/binary", "llama-server")
    settings.set_int("server/port", 8080)
    
    # Configure only openrouter API key via environment
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret-key")
    monkeypatch.setenv("OPENCODE_API_KEY", "")
    
    # Mock ServerManager
    mock_server = MagicMock()
    mock_server.is_running.return_value = False
    mock_server.start.return_value = True
    
    # Mock LlamaClient to capture construction and method calls
    client_calls = []
    class MockCloudLlamaClient:
        def __init__(self, host="http://localhost", port=8080, api_key=None, api_prefix=None):
            self.host = host
            self.port = port
            self.api_key = api_key
            client_calls.append(self)
            
        def chat_completion(self, messages, model=None, temperature=0.7, max_tokens=1024, stream=False):
            return {"choices": [{"message": {"content": f"Response from {model}"}}]}
            
    monkeypatch.setattr("justllama.server.council.LlamaClient", MockCloudLlamaClient)
    
    # Mock QThread.start to be a no-op
    monkeypatch.setattr("justllama.server.council.CouncilRunner.start", lambda self: None)
    
    manager = CouncilManager(settings, mock_server)
    
    # Capture signals
    progress_calls = []
    synthesis_prompt = []
    error_calls = []
    
    manager.progress_update.connect(progress_calls.append)
    manager.synthesis_ready.connect(synthesis_prompt.append)
    manager.error.connect(error_calls.append)
    
    # Start the council execution
    manager.start_council("What is 1+1?")
    manager._runner.run()
    
    # Verify results
    assert len(error_calls) == 0
    assert len(synthesis_prompt) == 1
    prompt = synthesis_prompt[0]
    
    assert "Model 1 (cloud nvidia) missing API key." in prompt
    assert "Response from google/gemini" in prompt
    assert "Model 3 (cloud opencode) missing API key." in prompt
    
    # Verify client constructions:
    # 1. Local client created at start
    # 2. openrouter cloud client created in loop
    assert len(client_calls) == 2
    assert client_calls[0].port == 8080
    assert client_calls[1].host == "https://openrouter.ai/api"
    assert client_calls[1].port is None
