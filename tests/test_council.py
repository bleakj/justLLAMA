"""Unit tests for the Council Mode orchestrator."""

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
