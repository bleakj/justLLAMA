import asyncio
import json

import threading
import shlex
from contextlib import AsyncExitStack
from PySide6.QtCore import QObject, Slot
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from justllama.config.settings import AppSettings


class McpManager(QObject):
    """Manages Model Context Protocol (MCP) server sessions.
    
    Runs an asyncio loop in a background thread to handle async stdio client connections
    and operations safely without blocking the Qt main thread.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._lock = None  # Lazily initialized in the loop
        
        # mapping from server_cmd -> (client_session, exit_stack)
        self._sessions = {}
        # mapping from tool_name -> client_session
        self._tool_to_session = {}

        # Listen for setting changes. Keep the AppSettings instance alive in
        # self so it (and its settings_changed signal) is not garbage-collected.
        self._settings = AppSettings()
        self._settings.settings_changed.connect(self._on_settings_changed)

        # Connect to configured servers on startup. connect_servers() is a safe
        # no-op when no servers are configured, so launch with an empty
        # mcp/servers list does not attempt a connection.
        self.connect_servers()


    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def connect_servers(self):
        """Trigger connection to configured MCP servers asynchronously."""
        asyncio.run_coroutine_threadsafe(self._connect_servers_async(), self._loop)

    def _on_settings_changed(self, key: str, value):
        if key in ("mcp/servers", "mcp/managed_skills"):
            print(f"[MCP] Config changed: {key}={value}. Reconnecting...")
            self.connect_servers()
    async def _connect_servers_async(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
            
        async with self._lock:
            # Clean up old sessions
            await self._cleanup_sessions_async()

            settings = AppSettings()
            servers = settings.mcp_servers
            print(f"[MCP] Connecting to servers: {servers}")
            # Merge enabled managed skills into the server list
            try:
                managed_skills_json = settings.get_json_string("mcp/managed_skills")
                if managed_skills_json:
                    managed_skills = json.loads(managed_skills_json)
                    if isinstance(managed_skills, list):
                        for skill in managed_skills:
                            if isinstance(skill, dict) and skill.get("enabled"):
                                cmd = skill.get("command", "").strip()
                                if cmd:
                                    servers.append(cmd)
            except (json.JSONDecodeError, Exception) as e:
                print(f"[MCP] Failed to parse managed_skills: {e}")
            print(f"[MCP] Full server list (including enabled skills): {servers}")
            for server_str in servers:
                if not server_str.strip():
                    continue
                try:
                    parts = shlex.split(server_str)
                    if not parts:
                        continue
                    cmd = parts[0]
                    args = parts[1:]
                    
                    server_params = StdioServerParameters(
                        command=cmd,
                        args=args,
                        env=None
                    )
                    
                    stack = AsyncExitStack()
                    transport = await stack.enter_async_context(stdio_client(server_params))
                    read, write = transport
                    
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    
                    self._sessions[server_str] = (session, stack)
                    print(f"[MCP] Successfully connected to server: {server_str}")
                except Exception as e:
                    print(f"[MCP] Failed to connect to server '{server_str}': {e}")
            
            await self._rebuild_tool_mappings_async()

    async def _cleanup_sessions_async(self):
        for server_str, (session, stack) in list(self._sessions.items()):
            try:
                await stack.aclose()
            except Exception as e:
                print(f"[MCP] Error closing session for {server_str}: {e}")
        self._sessions.clear()
        self._tool_to_session.clear()

    async def _rebuild_tool_mappings_async(self):
        self._tool_to_session.clear()
        for server_str, (session, stack) in self._sessions.items():
            try:
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, "tools") else tools_result
                for tool in tools:
                    name = tool.name if hasattr(tool, "name") else tool.get("name")
                    if name:
                        self._tool_to_session[name] = session
            except Exception as e:
                print(f"[MCP] Failed to list tools for {server_str}: {e}")

    @Slot(result=list)
    def get_openai_tools(self) -> list:
        """Fetch and format all tools from connected MCP servers into OpenAI function schema."""
        future = asyncio.run_coroutine_threadsafe(self._get_openai_tools_async(), self._loop)
        try:
            return future.result(timeout=5)
        except Exception as e:
            print(f"[MCP] Error fetching OpenAI tools: {e}")
            return []

    async def _get_openai_tools_async(self) -> list:
        # Re-fetch/verify tool mappings under the lock
        if self._lock is None:
            self._lock = asyncio.Lock()
        
        openai_tools = []
        for server_str, (session, stack) in self._sessions.items():
            try:
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, "tools") else tools_result
                for tool in tools:
                    name = tool.name if hasattr(tool, "name") else tool.get("name")
                    description = tool.description if hasattr(tool, "description") else tool.get("description", "")
                    input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else tool.get("inputSchema", {})
                    if hasattr(input_schema, "model_dump"):
                        input_schema = input_schema.model_dump()
                    
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": description,
                            "parameters": input_schema
                        }
                    })
            except Exception as e:
                print(f"[MCP] Error reading tools for {server_str}: {e}")
        return openai_tools

    @Slot(str, dict, result=str)
    def execute_tool(self, name: str, arguments: dict) -> str:
        """Execute a tool on the appropriate MCP server and return the string response."""
        future = asyncio.run_coroutine_threadsafe(self._execute_tool_async(name, arguments), self._loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            print(f"[MCP] Error executing tool '{name}': {e}")
            return f"Error executing tool '{name}': {e}"

    async def _execute_tool_async(self, name: str, arguments: dict) -> str:
        session = self._tool_to_session.get(name)
        if not session:
            raise ValueError(f"No active session for tool '{name}'")
        
        result = await session.call_tool(name, arguments)
        content_list = result.content if hasattr(result, "content") else result.get("content", [])
        
        texts = []
        for item in content_list:
            item_type = item.type if hasattr(item, "type") else item.get("type")
            if item_type == "text":
                text = item.text if hasattr(item, "text") else item.get("text", "")
                texts.append(text)
            elif item_type == "image":
                texts.append("[Image Content]")
            elif item_type == "resource":
                resource = item.resource if hasattr(item, "resource") else item.get("resource", None)
                texts.append(f"[Embedded Resource: {resource}]")
            else:
                texts.append(str(item))
        
        return "\n".join(texts)

    def shutdown(self):
        """Synchronously shutdown and clean up all connections and the background event loop."""
        future = asyncio.run_coroutine_threadsafe(self._cleanup_sessions_async(), self._loop)
        try:
            future.result(timeout=5)
        except Exception as e:
            print(f"[MCP] Error cleaning up sessions during shutdown: {e}")
        
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
