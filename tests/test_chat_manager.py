"""Unit and integration tests for justllama.server.chat_manager."""

import json
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QObject, Signal

from justllama.server.chat_manager import ChatRunner, ChatManager
from justllama.server.client import LlamaClient


# ---------------------------------------------------------------------------
# Test ChatRunner
# ---------------------------------------------------------------------------

def test_chat_runner_standard(qapp, monkeypatch):
    """Test ChatRunner with a standard chat completion (no tools).

    Verifies chunks are emitted and the final history is emitted via
    generation_complete upon [DONE].
    """
    # Mock AppSettings
    mock_settings = MagicMock()
    mock_settings.get_int.return_value = 8080
    monkeypatch.setattr("justllama.server.chat_manager.AppSettings", lambda: mock_settings)

    # Mock LlamaClient
    mock_client = MagicMock(spec=LlamaClient)
    monkeypatch.setattr("justllama.server.chat_manager.LlamaClient", lambda port: mock_client)

    class StandardResponse:
        def iter_lines(self):
            yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield b'data: {"choices": [{"delta": {"content": " world"}}]}'
            yield b'data: [DONE]'

        def close(self):
            pass

    resp = StandardResponse()
    captured_calls = []
    def spy_chat_completion(*args, **kwargs):
        kwargs_copy = dict(kwargs)
        kwargs_copy["messages"] = list(kwargs["messages"])
        captured_calls.append(kwargs_copy)
        return resp
    mock_client.chat_completion.side_effect = spy_chat_completion

    messages = [{"role": "user", "content": "Hi"}]
    params = {"model": "test-model", "temperature": 0.5, "max_tokens": 100}

    runner = ChatRunner(messages, params, mcp_manager=None)

    chunks = []
    completed = []
    errors = []
    runner.chunk_received.connect(chunks.append)
    runner.generation_complete.connect(completed.append)
    runner.error_occurred.connect(errors.append)

    # Run synchronously
    runner.run()

    # Assertions
    assert len(errors) == 0
    assert chunks == ["Hello", " world"]
    assert len(completed) == 1

    final_messages = completed[0]
    assert len(final_messages) == 2
    assert final_messages[0] == {"role": "user", "content": "Hi"}
    assert final_messages[1] == {"role": "assistant", "content": "Hello world"}

    # Verify LlamaClient was called with correct parameters
    assert len(captured_calls) == 1
    call_kwargs = captured_calls[0]
    assert call_kwargs["messages"] == [{"role": "user", "content": "Hi"}]
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["stream"] is True
    assert call_kwargs["tools"] is None
    assert call_kwargs["top_p"] == 0.95
    assert call_kwargs["top_k"] == 40
    assert call_kwargs["repeat_penalty"] == 1.1


def test_chat_runner_tool_calling(qapp, monkeypatch):
    """Test ChatRunner executing tools and feeding the results back.

    Verifies:
      1. Detects a tool call in the SSE stream.
      2. Executes the tool via McpManager.execute_tool().
      3. Appends the tool call assistant message and the tool result message.
      4. Calls LlamaClient.chat_completion again for the final response.
    """
    # Mock AppSettings
    mock_settings = MagicMock()
    mock_settings.get_int.return_value = 8080
    monkeypatch.setattr("justllama.server.chat_manager.AppSettings", lambda: mock_settings)

    # Mock LlamaClient
    mock_client = MagicMock(spec=LlamaClient)
    monkeypatch.setattr("justllama.server.chat_manager.LlamaClient", lambda port: mock_client)

    # Mock McpManager
    mock_mcp = MagicMock()
    fake_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a location",
                "parameters": {}
            }
        }
    ]
    mock_mcp.get_openai_tools.return_value = fake_tools
    mock_mcp.execute_tool.return_value = "sunny, 20C"

    # First completion yields tool call chunks
    class ToolCallResponse:
        def iter_lines(self):
            yield b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "get_weather", "arguments": "{\\"loc"}}]}}]}'
            yield b'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ation\\": \\"Paris\\"}"}}]}}]}'
            yield b'data: [DONE]'

        def close(self):
            pass

    # Second completion yields the text response
    class TextResponse:
        def iter_lines(self):
            yield b'data: {"choices": [{"delta": {"content": "The weather is sunny."}}]}'
            yield b'data: [DONE]'

        def close(self):
            pass

    responses = iter([ToolCallResponse(), TextResponse()])
    captured_calls = []
    def spy_chat_completion(*args, **kwargs):
        kwargs_copy = dict(kwargs)
        kwargs_copy["messages"] = list(kwargs["messages"])
        captured_calls.append(kwargs_copy)
        return next(responses)
    mock_client.chat_completion.side_effect = spy_chat_completion
    messages = [{"role": "user", "content": "What's the weather in Paris?"}]
    params = {"model": "test-model"}

    runner = ChatRunner(messages, params, mcp_manager=mock_mcp)

    chunks = []
    completed = []
    tool_signals = []
    errors = []

    runner.chunk_received.connect(chunks.append)
    runner.generation_complete.connect(completed.append)
    runner.tool_call_detected.connect(lambda name, args: tool_signals.append((name, args)))
    runner.error_occurred.connect(errors.append)

    # Run synchronously
    runner.run()

    # Assertions
    assert len(errors) == 0
    assert chunks == ["The weather is sunny."]
    assert len(tool_signals) == 1
    assert tool_signals[0] == ("get_weather", '{"location": "Paris"}')

    # McpManager execute_tool should have been called
    mock_mcp.execute_tool.assert_called_once_with("get_weather", {"location": "Paris"})

    # Check final history
    assert len(completed) == 1
    final_history = completed[0]
    assert len(final_history) == 4
    assert final_history[0] == {"role": "user", "content": "What's the weather in Paris?"}

    # Assistant tool call message
    assert final_history[1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"location": "Paris"}'
                }
            }
        ]
    }

    # Tool result message
    assert final_history[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "get_weather",
        "content": "sunny, 20C"
    }

    # Final assistant response
    assert final_history[3] == {
        "role": "assistant",
        "content": "The weather is sunny."
    }

    # Verify LlamaClient was called twice
    assert len(captured_calls) == 2
    
    # First call had tools injected
    assert captured_calls[0]["tools"] == fake_tools
    assert captured_calls[0]["messages"] == [{"role": "user", "content": "What's the weather in Paris?"}]

    # Second call had updated messages with tool result
    assert captured_calls[1]["messages"] == final_history[:3]


def test_chat_runner_stop(qapp, monkeypatch):
    """Test that calling stop() mid-stream closes the connection and exits."""
    # Mock AppSettings
    mock_settings = MagicMock()
    mock_settings.get_int.return_value = 8080
    monkeypatch.setattr("justllama.server.chat_manager.AppSettings", lambda: mock_settings)

    # Mock LlamaClient
    mock_client = MagicMock(spec=LlamaClient)
    monkeypatch.setattr("justllama.server.chat_manager.LlamaClient", lambda port: mock_client)

    runner = None

    class CancellableResponse:
        def __init__(self):
            self.is_closed = False

        def iter_lines(self):
            yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            # Trigger cancellation mid-stream
            if runner:
                runner.stop()
            yield b'data: {"choices": [{"delta": {"content": " world"}}]}'

        def close(self):
            self.is_closed = True

    resp = CancellableResponse()
    mock_client.chat_completion.return_value = resp

    messages = [{"role": "user", "content": "Hi"}]
    runner = ChatRunner(messages, {}, mcp_manager=None)

    chunks = []
    completed = []
    runner.chunk_received.connect(chunks.append)
    runner.generation_complete.connect(completed.append)

    runner.run()

    # Assertions
    assert runner._is_stopped is True
    assert resp.is_closed is True
    assert chunks == ["Hello"]
    # Should not complete generation on stop
    assert len(completed) == 0


def test_chat_runner_error(qapp, monkeypatch):
    """Test that errors during runner loop are caught and emitted."""
    # Mock AppSettings
    mock_settings = MagicMock()
    mock_settings.get_int.return_value = 8080
    monkeypatch.setattr("justllama.server.chat_manager.AppSettings", lambda: mock_settings)

    # Mock LlamaClient to raise an exception
    mock_client = MagicMock(spec=LlamaClient)
    mock_client.chat_completion.side_effect = RuntimeError("Connection refused")
    monkeypatch.setattr("justllama.server.chat_manager.LlamaClient", lambda port: mock_client)

    runner = ChatRunner([], {}, mcp_manager=None)

    errors = []
    runner.error_occurred.connect(errors.append)

    runner.run()

    assert errors == ["Connection refused"]


def test_chat_runner_robustness(qapp, monkeypatch):
    """Test runner resilience to malformed JSON and noise lines in SSE stream."""
    # Mock AppSettings
    mock_settings = MagicMock()
    mock_settings.get_int.return_value = 8080
    monkeypatch.setattr("justllama.server.chat_manager.AppSettings", lambda: mock_settings)

    # Mock LlamaClient
    mock_client = MagicMock(spec=LlamaClient)
    monkeypatch.setattr("justllama.server.chat_manager.LlamaClient", lambda port: mock_client)

    class NoiseResponse:
        def iter_lines(self):
            yield b''  # empty line
            yield b': ping'  # comment line
            yield b'data: {invalid json}'  # malformed JSON
            yield b'data: {"choices": [{"delta": {"content": "Valid"}}]}'
            yield b'data: [DONE]'
            yield b'data: {"choices": [{"delta": {"content": "ignored"}}]}'  # after DONE

        def close(self):
            pass

    mock_client.chat_completion.return_value = NoiseResponse()

    runner = ChatRunner([], {}, mcp_manager=None)

    chunks = []
    completed = []
    runner.chunk_received.connect(chunks.append)
    runner.generation_complete.connect(completed.append)

    runner.run()

    assert chunks == ["Valid"]
    assert len(completed) == 1
    assert completed[0] == [{"role": "assistant", "content": "Valid"}]


# ---------------------------------------------------------------------------
# Test ChatManager
# ---------------------------------------------------------------------------

def test_chat_manager_signals(qapp, monkeypatch):
    """Test ChatManager forwards signals from the runner."""
    class FakeRunner(QObject):
        chunk_received = Signal(str)
        generation_complete = Signal(list)
        error_occurred = Signal(str)
        tool_call_detected = Signal(str, str)

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.start = MagicMock()
            self.isRunning = MagicMock(return_value=False)

    monkeypatch.setattr("justllama.server.chat_manager.ChatRunner", FakeRunner)

    manager = ChatManager()

    chunks = []
    completed = []
    errors = []
    tools = []

    manager.chunk_received.connect(chunks.append)
    manager.generation_complete.connect(completed.append)
    manager.error_occurred.connect(errors.append)
    manager.tool_call_detected.connect(lambda name, args: tools.append((name, args)))

    manager.send_message([], {})

    # Emit signals from the runner
    runner = manager._runner
    runner.chunk_received.emit("chunk1")
    runner.generation_complete.emit([{"role": "assistant", "content": "done"}])
    runner.error_occurred.emit("some error")
    runner.tool_call_detected.emit("tool_name", '{"arg": 1}')

    assert chunks == ["chunk1"]
    assert completed == [[{"role": "assistant", "content": "done"}]]
    assert errors == ["some error"]
    assert tools == [("tool_name", '{"arg": 1}')]


def test_chat_manager_stop_generation(qapp, monkeypatch):
    """Test ChatManager stops any active runner when stop_generation is called."""
    class FakeRunner(QObject):
        chunk_received = Signal(str)
        generation_complete = Signal(list)
        error_occurred = Signal(str)
        tool_call_detected = Signal(str, str)

        def __init__(self, *args, **kwargs):
            super().__init__()
            self.start = MagicMock()
            self.stop = MagicMock()
            self.wait = MagicMock()
            self.isRunning = MagicMock(return_value=True)

    monkeypatch.setattr("justllama.server.chat_manager.ChatRunner", FakeRunner)

    manager = ChatManager()
    manager.send_message([], {})

    runner = manager._runner
    assert runner is not None

    manager.stop_generation()

    runner.stop.assert_called_once()
    runner.wait.assert_called_once()
    assert manager._runner is None
