import json
from PySide6.QtCore import QObject, QThread, Signal, Slot
from justllama.server.client import LlamaClient
from justllama.config.settings import AppSettings


class ChatRunner(QThread):
    """Worker thread that executes the chat completion loop.
    
    Communicates with llama.cpp, parses incoming SSE chunks, intercepts
    tool calls, executes them via McpManager, and feeds results back.
    """

    chunk_received = Signal(str)
    generation_complete = Signal(list)
    error_occurred = Signal(str)
    tool_call_detected = Signal(str, str)  # tool_name, tool_args

    def __init__(self, messages: list, params: dict, mcp_manager, parent=None):
        super().__init__(parent)
        self.messages = list(messages)
        self.params = dict(params)
        self.mcp_manager = mcp_manager
        self._is_stopped = False
        self._current_response = None

    def run(self):
        try:
            self._execute_loop()
        except Exception as e:
            if not self._is_stopped:
                import traceback
                traceback.print_exc()
                self.error_occurred.emit(str(e))

    def stop(self):
        """Request the runner to abort immediately."""
        self._is_stopped = True
        if self._current_response:
            try:
                self._current_response.close()
            except Exception:
                pass

    def _execute_loop(self):
        settings = AppSettings()
        port = settings.get_int("server/port") or 8080
        client = LlamaClient(port=port)

        max_loops = 10
        loop_count = 0

        while loop_count < max_loops and not self._is_stopped:
            loop_count += 1
            
            # Fetch tools if MCP is available and has servers configured
            tools = None
            if self.mcp_manager:
                mcp_tools = self.mcp_manager.get_openai_tools()
                if mcp_tools:
                    tools = mcp_tools

            # Prepare chat completion parameters
            model = self.params.get("model", "default")
            temperature = self.params.get("temperature", 0.7)
            max_tokens = self.params.get("max_tokens", 2048)
            
            extra_params = {
                "top_p": self.params.get("top_p", 0.95),
                "top_k": self.params.get("top_k", 40),
                "repeat_penalty": self.params.get("repeat_penalty", 1.1),
            }

            # If there are tools, pass them. Otherwise omit to revert perfectly to standard completion
            resp = client.chat_completion(
                messages=self.messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                tools=tools,
                **extra_params
            )
            
            self._current_response = resp
            tool_calls_accumulated = {}
            full_content = ""

            try:
                for line in resp.iter_lines():
                    if self._is_stopped:
                        break
                    if not line:
                        continue
                    
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data:"):
                        data_str = line_str[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            parsed = json.loads(data_str)
                        except Exception:
                            continue
                        
                        delta = parsed.get("choices", [{}])[0].get("delta", {})
                        
                        # Accumulate content chunks
                        content_chunk = delta.get("content")
                        if content_chunk:
                            full_content += content_chunk
                            self.chunk_received.emit(content_chunk)
                        
                        # Accumulate tool calls chunks
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_accumulated:
                                    tool_calls_accumulated[idx] = {
                                        "id": tc.get("id"),
                                        "name": tc.get("function", {}).get("name"),
                                        "arguments": []
                                    }
                                else:
                                    if tc.get("id") is not None:
                                        tool_calls_accumulated[idx]["id"] = tc.get("id")
                                    if tc.get("function", {}).get("name") is not None:
                                        tool_calls_accumulated[idx]["name"] = tc.get("function", {}).get("name")
                                
                                arg_chunk = tc.get("function", {}).get("arguments")
                                if arg_chunk:
                                    tool_calls_accumulated[idx]["arguments"].append(arg_chunk)
            finally:
                resp.close()
                self._current_response = None

            if self._is_stopped:
                break

            # If tool calls were requested, process them
            if tool_calls_accumulated:
                tool_calls_list = []
                for idx in sorted(tool_calls_accumulated.keys()):
                    tc = tool_calls_accumulated[idx]
                    full_args_str = "".join(tc["arguments"])
                    tool_calls_list.append({
                        "id": tc["id"] or f"call_{idx}",
                        "type": "function",
                        "function": {
                            "name": tc["name"] or "",
                            "arguments": full_args_str
                        }
                    })

                # Append assistant message with tool calls to history
                assistant_msg = {
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": tool_calls_list
                }
                self.messages.append(assistant_msg)

                # Execute each tool call
                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    args_str = tc["function"]["arguments"]
                    
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except Exception:
                        args = {}
                    
                    self.tool_call_detected.emit(name, json.dumps(args))
                    print(f"[ChatRunner] Executing tool '{name}' with args {args}")
                    
                    # Execute tool synchronously within this worker thread
                    if self.mcp_manager:
                        tool_result = self.mcp_manager.execute_tool(name, args)
                    else:
                        tool_result = f"Error: McpManager not available to execute '{name}'"
                    
                    print(f"[ChatRunner] Tool '{name}' returned result: {tool_result}")
                    
                    # Append tool result to history
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": name,
                        "content": tool_result
                    }
                    self.messages.append(tool_msg)
                
                # Continue loop to call llama.cpp again with the tool results added to context
                continue
            
            else:
                # No tool calls were made; generation is complete
                if full_content:
                    self.messages.append({
                        "role": "assistant",
                        "content": full_content
                    })
                self.generation_complete.emit(self.messages)
                break


class ChatManager(QObject):
    """Manages chat completion requests and orchestrates ChatRunners."""

    chunk_received = Signal(str)
    generation_complete = Signal(list)
    error_occurred = Signal(str)
    tool_call_detected = Signal(str, str)

    def __init__(self, mcp_manager=None, parent=None):
        super().__init__(parent)
        self.mcp_manager = mcp_manager
        self._runner = None

    @Slot(list, dict)
    def send_message(self, messages: list, params: dict):
        """Slot called from QML to launch the chat completions loop."""
        self.stop_generation()

        self._runner = ChatRunner(messages, params, self.mcp_manager)
        self._runner.chunk_received.connect(self.chunk_received)
        self._runner.generation_complete.connect(self._on_generation_complete)
        self._runner.error_occurred.connect(self.error_occurred)
        self._runner.tool_call_detected.connect(self.tool_call_detected)
        self._runner.start()

    @Slot()
    def stop_generation(self):
        """Stop the currently active runner if it is running."""
        if self._runner and self._runner.isRunning():
            self._runner.stop()
            self._runner.wait()
            self._runner = None

    def _on_generation_complete(self, messages: list):
        self.generation_complete.emit(messages)
