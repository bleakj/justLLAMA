import pytest
import threading
import asyncio
from unittest.mock import MagicMock, AsyncMock
from PySide6.QtCore import QSettings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def settings(qapp, tmp_path, monkeypatch):
    """Return an AppSettings instance backed by a temporary INI file."""
    settings_file = str(tmp_path / "test_settings_mcp.conf")

    from justllama.config import settings as settings_mod

    class _TestQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_file, QSettings.IniFormat)

    monkeypatch.setattr(settings_mod, "QSettings", _TestQSettings)

    from justllama.config.settings import AppSettings
    instance = AppSettings()
    
    # Automatically patch AppSettings inside mcp.py to return this test instance.
    # This guarantees that signals emitted by settings are received by McpManager.
    monkeypatch.setattr("justllama.server.mcp.AppSettings", lambda: instance)
    
    yield instance


@pytest.fixture
def mock_mcp(monkeypatch):
    """Mock stdio_client and ClientSession from the mcp package using monkeypatch."""
    created_sessions = []
    tools_pool = []
    
    # We use a side effect for ClientSession to create a fresh mock session
    # upon every invocation, and track all created sessions.
    def create_session_context(read, write):
        session = MagicMock(name=f"ClientSession_{len(created_sessions)}")
        session.initialize = AsyncMock()
        
        # Pop pre-configured tools from the pool for this session if available
        tools = tools_pool.pop(0) if tools_pool else []
        session.list_tools = AsyncMock(return_value=tools)
        session.call_tool = AsyncMock()
        
        created_sessions.append(session)
        
        mock_session_context = MagicMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        return mock_session_context

    mock_read = MagicMock(name="read")
    mock_write = MagicMock(name="write")
    mock_transport = (mock_read, mock_write)
    
    mock_stdio_context = MagicMock()
    mock_stdio_context.__aenter__ = AsyncMock(return_value=mock_transport)
    mock_stdio_context.__aexit__ = AsyncMock(return_value=None)
    
    mock_stdio_client = MagicMock(return_value=mock_stdio_context)
    mock_client_session = MagicMock(side_effect=create_session_context)
    
    monkeypatch.setattr("justllama.server.mcp.stdio_client", mock_stdio_client)
    monkeypatch.setattr("justllama.server.mcp.ClientSession", mock_client_session)
    
    return {
        "stdio_client": mock_stdio_client,
        "client_session": mock_client_session,
        "created_sessions": created_sessions,
        "tools_pool": tools_pool,
        "read": mock_read,
        "write": mock_write
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_initial_connection(settings, mock_mcp, monkeypatch):
    """Test that McpManager initiates connection to configured servers on startup."""
    from justllama.server.mcp import McpManager
    
    # Configure initial servers
    settings.set_list("mcp/servers", ["server1 arg1", "server2"])
    
    # Setup thread synchronization event
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
            
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    # Instantiate McpManager (starts thread and runs connect)
    manager = McpManager()
    
    # Wait for the async connection task to finish
    assert event.wait(timeout=2)
    
    # Verify stdio_client was called for both servers
    assert mock_mcp["stdio_client"].call_count == 2
    
    calls = mock_mcp["stdio_client"].call_args_list
    
    # First server parameter checks
    params_1 = calls[0][0][0]
    assert params_1.command == "server1"
    assert params_1.args == ["arg1"]
    
    # Second server parameter checks
    params_2 = calls[1][0][0]
    assert params_2.command == "server2"
    assert params_2.args == []
    
    manager.shutdown()


def test_no_connect_when_empty(settings, mock_mcp, monkeypatch, capsys):
    """Test that McpManager does NOT attempt to connect when no MCP servers
    are configured (the default mcp/servers is an empty list)."""
    from justllama.server.mcp import McpManager

    # Default mcp/servers == [] -> connect_servers() is a guarded no-op.
    manager = McpManager()
    manager.shutdown()

    # No connection attempt should have been made for an empty config.
    assert mock_mcp["stdio_client"].call_count == 0

    # The startup "Connecting to servers" log line must not be printed.
    captured = capsys.readouterr()
    assert "Connecting to servers" not in captured.out


def test_settings_changes_trigger_reconnection(settings, mock_mcp, monkeypatch):
    """Test that setting changes to mcp/servers trigger a reconnection."""
    from justllama.server.mcp import McpManager
    # Configure an initial server so the guarded startup connect actually fires.
    settings.set_list("mcp/servers", ["initial_server"])
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    connect_count = 0
    
    async def wrapper(self, *args, **kwargs):
        nonlocal connect_count
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            connect_count += 1
            event.set()
            
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    # Instantiate manager (triggers initial connect to the configured server)
    manager = McpManager()
    assert event.wait(timeout=2)
    assert connect_count == 1
    
    # 2. Change an unrelated setting (reconnection should NOT trigger)
    event.clear()
    settings.set_string("chat/mode", "council")
    assert not event.wait(timeout=0.2)
    assert connect_count == 1
    
    # 3. Change mcp/servers setting (reconnection SHOULD trigger)
    event.clear()
    settings.set_list("mcp/servers", ["new_server"])
    assert event.wait(timeout=2)
    assert connect_count == 2
    
    # Verify stdio_client was called with the new server details
    calls = mock_mcp["stdio_client"].call_args_list
    params = calls[-1][0][0]
    assert params.command == "new_server"
    assert params.args == []
    
    manager.shutdown()


def test_get_openai_tools_mapping(settings, mock_mcp, monkeypatch):
    """Test that get_openai_tools maps schemas to OpenAI function calling structure."""
    from justllama.server.mcp import McpManager
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    # Configure mock tools with different structures (dict and object/Pydantic-like)
    tool_dict = {
        "name": "calculator",
        "description": "Perform math operations",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"}
            },
            "required": ["a", "b"]
        }
    }
    
    class MockInputSchema:
        def model_dump(self):
            return {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                }
            }
            
    class MockTool:
        name = "logger"
        description = "Log a message"
        inputSchema = MockInputSchema()
        
    # Queue up the tools for the first session
    mock_mcp["tools_pool"].append([tool_dict, MockTool()])
    
    settings.set_list("mcp/servers", ["server1"])
    manager = McpManager()
    assert event.wait(timeout=2)
    
    # Retrieve OpenAI tools
    openai_tools = manager.get_openai_tools()
    
    # Assert correct conversion and formatting
    assert len(openai_tools) == 2
    
    # Assert tool 1 (dict) mapping
    assert openai_tools[0] == {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Perform math operations",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"}
                },
                "required": ["a", "b"]
            }
        }
    }
    
    # Assert tool 2 (object) mapping
    assert openai_tools[1] == {
        "type": "function",
        "function": {
            "name": "logger",
            "description": "Log a message",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                }
            }
        }
    }
    
    manager.shutdown()


def test_routing_to_appropriate_session(settings, mock_mcp, monkeypatch):
    """Test that execute_tool routes the call to the appropriate session."""
    from justllama.server.mcp import McpManager
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    # Queue tools for session 1 and session 2
    mock_mcp["tools_pool"].extend([
        [{"name": "tool_a", "description": "Tool A", "inputSchema": {}}],
        [{"name": "tool_b", "description": "Tool B", "inputSchema": {}}]
    ])
    
    # Configure two servers
    settings.set_list("mcp/servers", ["server1", "server2"])
    manager = McpManager()
    assert event.wait(timeout=2)
    
    assert len(mock_mcp["created_sessions"]) == 2
    session_1 = mock_mcp["created_sessions"][0]
    session_2 = mock_mcp["created_sessions"][1]
    
    # Execute tool_a and verify routing to session_1
    session_1.call_tool.return_value = {"content": [{"type": "text", "text": "result A"}]}
    res_a = manager.execute_tool("tool_a", {"val": 100})
    assert res_a == "result A"
    session_1.call_tool.assert_called_once_with("tool_a", {"val": 100})
    session_2.call_tool.assert_not_called()
    
    # Reset mocks
    session_1.call_tool.reset_mock()
    session_2.call_tool.reset_mock()
    
    # Execute tool_b and verify routing to session_2
    session_2.call_tool.return_value = {"content": [{"type": "text", "text": "result B"}]}
    res_b = manager.execute_tool("tool_b", {"val": 200})
    assert res_b == "result B"
    session_2.call_tool.assert_called_once_with("tool_b", {"val": 200})
    session_1.call_tool.assert_not_called()
    
    manager.shutdown()


def test_execute_tool_content_parsing(settings, mock_mcp, monkeypatch):
    """Test that execute_tool parses text, image, resource, and unknown content types."""
    from justllama.server.mcp import McpManager
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    # Queue tool for session
    mock_mcp["tools_pool"].append([
        {"name": "parser", "description": "Parser tool", "inputSchema": {}}
    ])
    
    settings.set_list("mcp/servers", ["server1"])
    manager = McpManager()
    assert event.wait(timeout=2)
    
    session = mock_mcp["created_sessions"][0]
    
    # Case 1: Text type (dict)
    session.call_tool.return_value = {"content": [{"type": "text", "text": "Hello text"}]}
    assert manager.execute_tool("parser", {}) == "Hello text"
    
    # Case 2: Image type (dict)
    session.call_tool.return_value = {"content": [{"type": "image"}]}
    assert manager.execute_tool("parser", {}) == "[Image Content]"
    
    # Case 3: Resource type (dict)
    session.call_tool.return_value = {"content": [{"type": "resource", "resource": "uri_1"}]}
    assert manager.execute_tool("parser", {}) == "[Embedded Resource: uri_1]"
    
    # Case 4: Unknown type (dict)
    session.call_tool.return_value = {"content": [{"type": "other_type"}]}
    assert "{'type': 'other_type'}" in manager.execute_tool("parser", {})
    
    # Case 5: Multiple mixed items
    session.call_tool.return_value = {
        "content": [
            {"type": "text", "text": "Line 1"},
            {"type": "image"},
            {"type": "resource", "resource": "uri_2"}
        ]
    }
    assert manager.execute_tool("parser", {}) == "Line 1\n[Image Content]\n[Embedded Resource: uri_2]"
    
    # Case 6: Object responses instead of dicts
    class MockTextItem:
        type = "text"
        text = "Object text"
        
    class MockImageItem:
        type = "image"
        
    class MockResourceItem:
        type = "resource"
        resource = "object_uri"
        
    class MockResult:
        content = [MockTextItem(), MockImageItem(), MockResourceItem()]
        
    session.call_tool.return_value = MockResult()
    assert manager.execute_tool("parser", {}) == "Object text\n[Image Content]\n[Embedded Resource: object_uri]"
    
    manager.shutdown()


def test_execute_tool_unknown(settings, mock_mcp, monkeypatch):
    """Test execute_tool with a tool that does not have an active session mapping."""
    from justllama.server.mcp import McpManager
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    settings.set_list("mcp/servers", ["server1"])
    manager = McpManager()
    assert event.wait(timeout=2)
    
    # Unknown tool call should return an error message
    res = manager.execute_tool("unknown_tool", {})
    assert "Error executing tool 'unknown_tool'" in res
    assert "No active session for tool" in res
    
    manager.shutdown()


def test_get_openai_tools_error_handling(settings, mock_mcp, monkeypatch):
    """Test that list_tools errors in get_openai_tools are caught and handled gracefully."""
    from justllama.server.mcp import McpManager
    
    event = threading.Event()
    original_connect = McpManager._connect_servers_async
    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()
    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)
    
    mock_mcp["tools_pool"].append([
        {"name": "tool1", "description": "Desc", "inputSchema": {}}
    ])
    
    settings.set_list("mcp/servers", ["server1"])
    manager = McpManager()
    assert event.wait(timeout=2)
    
    session = mock_mcp["created_sessions"][0]
    session.list_tools.side_effect = Exception("Connection lost")
    
    # Should not raise exception, return empty list
    openai_tools = manager.get_openai_tools()
    assert openai_tools == []
    
    manager.shutdown()


def test_mcp_custom_environment_variables(settings, mock_mcp, monkeypatch):
    """Test that McpManager passes configured custom environment variables to StdioServerParameters."""
    import json
    import os
    from unittest.mock import MagicMock
    from justllama.server.mcp import McpManager
    import justllama.server.mcp

    # 1. Setup mock server command and custom environment variables
    server_cmd = "my_custom_server arg1"
    custom_env = {"MY_TEST_VAR": "TEST_VAL", "ANOTHER_VAR": "ANOTHER_VAL"}

    # Configure mcp/servers
    settings.set_list("mcp/servers", [server_cmd])

    # Configure mcp/servers_config as a JSON string with the env dictionary
    config_data = [
        {
            "command": server_cmd,
            "env": custom_env
        }
    ]
    settings.set_json_string("mcp/servers_config", json.dumps(config_data))

    # 2. Spy on StdioServerParameters to capture arguments passed during instantiation
    original_params_class = justllama.server.mcp.StdioServerParameters
    mock_params_class = MagicMock(side_effect=original_params_class)
    monkeypatch.setattr("justllama.server.mcp.StdioServerParameters", mock_params_class)

    # 3. Setup thread synchronization event
    event = threading.Event()
    original_connect = McpManager._connect_servers_async

    async def wrapper(self, *args, **kwargs):
        try:
            await original_connect(self, *args, **kwargs)
        finally:
            event.set()

    monkeypatch.setattr(McpManager, "_connect_servers_async", wrapper)

    # 4. Instantiate McpManager (starts thread and runs connect)
    manager = McpManager()

    # Wait for the async connection task to finish
    assert event.wait(timeout=2)

    # 5. Verify StdioServerParameters was instantiated with correct arguments
    mock_params_class.assert_called_once()
    args_passed = mock_params_class.call_args[1]

    assert args_passed["command"] == "my_custom_server"
    assert args_passed["args"] == ["arg1"]

    # Verify the env dictionary includes custom environment variables merged with os.environ
    passed_env = args_passed["env"]
    for k, v in custom_env.items():
        assert passed_env.get(k) == v

    # Verify that existing os.environ keys are still preserved
    for k, v in os.environ.items():
        if k not in custom_env:
            assert passed_env.get(k) == v

    manager.shutdown()
