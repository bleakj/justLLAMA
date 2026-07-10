"""Tests for the TerminalManager class and related native agent skills."""

import os
import queue
import threading
import time
import pytest
from PySide6.QtCore import Qt

from justllama.server.terminal_manager import TerminalManager
from justllama.server.skills.terminal_skill import TerminalRunCommand, TerminalSendKeys


@pytest.fixture
def terminal_manager_isolated(qapp):
    """Provides an isolated, clean TerminalManager instance that is stopped on teardown."""
    tm = TerminalManager()
    yield tm
    tm.stop_session()


@pytest.fixture
def clean_singleton_manager(qapp):
    """Resets and cleans the shared singleton terminal_manager before and after tests."""
    from justllama.server.terminal_manager import terminal_manager
    terminal_manager.stop_session()
    with terminal_manager.queues_lock:
        terminal_manager.queues.clear()
    with terminal_manager._history_lock:
        terminal_manager._history = ""
    
    yield terminal_manager

    terminal_manager.stop_session()
    with terminal_manager.queues_lock:
        terminal_manager.queues.clear()
    with terminal_manager._history_lock:
        terminal_manager._history = ""


# ------------------------------------------------------------------
# TerminalManager Tests
# ------------------------------------------------------------------

class TestTerminalManager:
    def test_start_and_stop_session(self, terminal_manager_isolated):
        tm = terminal_manager_isolated
        assert tm.process is None
        assert not tm._running

        tm.start_session()
        assert tm._running
        assert tm.process is not None
        assert tm.process.poll() is None  # Running
        assert tm.master_fd is not None

        # Idempotence test: calling start_session again does not spawn a new process
        old_process = tm.process
        tm.start_session()
        assert tm.process is old_process

        tm.stop_session()
        assert not tm._running
        assert tm.process is None
        assert tm.master_fd is None

    def test_send_keys_and_data_received(self, terminal_manager_isolated):
        tm = terminal_manager_isolated
        
        received_data = []
        data_event = threading.Event()

        def on_data(text):
            received_data.append(text)
            if "hello_unique_marker" in "".join(received_data):
                data_event.set()

        tm.data_received.connect(on_data, Qt.DirectConnection)
        tm.start_session()

        # Send command to print marker
        tm.send_keys("echo hello_unique_marker\n")

        # Wait for the output to contain our marker
        success = data_event.wait(timeout=5.0)
        assert success, f"Failed to receive echo output. Received so far: {''.join(received_data)}"
        
        merged = "".join(received_data)
        assert "hello_unique_marker" in merged

    def test_queue_registration(self, terminal_manager_isolated):
        tm = terminal_manager_isolated
        tm.start_session()

        q = queue.Queue()
        tm.register_queue(q)

        # Send unique queue test message
        tm.send_keys("echo test_queue_msg\n")

        chunks = []
        start_time = time.time()
        while time.time() - start_time < 3.0:
            try:
                chunk = q.get(timeout=0.1)
                chunks.append(chunk)
                if "test_queue_msg" in "".join(chunks):
                    break
            except queue.Empty:
                continue

        merged = "".join(chunks)
        assert "test_queue_msg" in merged

        # Unregister the queue
        tm.unregister_queue(q)

        # Flush the queue
        while not q.empty():
            q.get_nowait()

        # Send another message
        tm.send_keys("echo test_queue_msg2\n")

        # Verify no further data is sent to the queue
        time.sleep(0.5)
        assert q.empty()

    def test_get_history(self, terminal_manager_isolated):
        tm = terminal_manager_isolated
        tm.start_session()

        tm.send_keys("echo history_test_value\n")

        # Poll history until the value appears
        start_time = time.time()
        success = False
        while time.time() - start_time < 3.0:
            history = tm.get_history()
            if "history_test_value" in history:
                success = True
                break
            time.sleep(0.1)

        assert success
        assert "history_test_value" in tm.get_history()


# ------------------------------------------------------------------
# TerminalRunCommand Skill Tests
# ------------------------------------------------------------------

class TestTerminalRunCommand:
    def test_execute_success(self, clean_singleton_manager):
        skill = TerminalRunCommand()
        assert skill.get_name() == "Terminal Run Command"
        assert skill.skill_id == "terminal_run_command"
        assert "parameters" in skill.get_tool_schema()["function"]

        result = skill.execute({"command": "echo 'hello world'"})
        assert "Command completed with exit code 0" in result
        assert "hello world" in result

    def test_execute_invalid_args(self, clean_singleton_manager):
        skill = TerminalRunCommand()

        # Missing command
        result1 = skill.execute({})
        assert "required" in result1

        # Non-string command
        result2 = skill.execute({"command": 123})
        assert "required" in result2

    def test_execute_timeout(self, clean_singleton_manager):
        skill = TerminalRunCommand()

        # Run sleep command with a short timeout
        result = skill.execute({"command": "sleep 5", "timeout": 1.0})
        assert "Command timed out or is still running" in result
        assert "timeout=1.0s" in result

    def test_execute_cancellation(self, clean_singleton_manager):
        skill = TerminalRunCommand()

        cancel_check = lambda: True
        result = skill.execute({"command": "echo 'hello'", "timeout": 5.0}, cancel_check=cancel_check)
        assert "[Command execution cancelled by user]" in result


# ------------------------------------------------------------------
# TerminalSendKeys Skill Tests
# ------------------------------------------------------------------

class TestTerminalSendKeys:
    def test_execute_success(self, clean_singleton_manager):
        skill = TerminalSendKeys()
        assert skill.get_name() == "Terminal Send Keys"
        assert skill.skill_id == "terminal_send_keys"
        assert "parameters" in skill.get_tool_schema()["function"]

        result = skill.execute({"keys": "echo 'sent_keys_test'\n"})
        assert "Keys sent. New terminal output:" in result
        assert "sent_keys_test" in result

    def test_execute_invalid_args(self, clean_singleton_manager):
        skill = TerminalSendKeys()

        # Missing keys
        result1 = skill.execute({})
        assert "must be a string" in result1

        # Non-string keys
        result2 = skill.execute({"keys": 123})
        assert "must be a string" in result2

        # Invalid type of keys
        result3 = skill.execute({"keys": None})
        assert "must be a string" in result3

    def test_execute_cancellation(self, clean_singleton_manager):
        skill = TerminalSendKeys()

        cancel_check = lambda: True
        result = skill.execute({"keys": "echo 'hello'\n"}, cancel_check=cancel_check)
        assert "Keys sent. New terminal output:" in result
