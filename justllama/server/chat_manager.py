import json
import time
from PySide6.QtCore import QObject, QThread, Signal, Slot
from justllama.server.client import LlamaClient
from justllama.config.settings import AppSettings


class ContextMonitor(QThread):
    """Background thread that monitors context token usage.

    Polls the /slots endpoint periodically and emits signals when context
    usage exceeds thresholds, enabling auto-compaction.
    """

    context_nearly_full = Signal(int, int)  # used_tokens, max_tokens
    context_warning = Signal(int, int)  # used_tokens, max_tokens (at 60%)

    def __init__(self, port: int = 8080, parent=None):
        super().__init__(parent)
        self._port = port
        self._running = True
        self._poll_interval = 5  # seconds
        self._warning_threshold = 0.60  # 60% = warning
        self._critical_threshold = 0.80  # 80% = auto-compact

    def stop(self):
        """Request the monitor to stop."""
        self._running = False

    def run(self):
        client = LlamaClient(port=self._port)
        warned = False

        while self._running:
            try:
                slots = client.slots(timeout=2)
                for slot in slots:
                    if not slot.get("is_processing", False):
                        continue

                    n_ctx = slot.get("n_ctx", 0)
                    n_used = slot.get("n_token_usage", 0)

                    if n_ctx <= 0:
                        continue

                    usage_ratio = n_used / n_ctx

                    if usage_ratio >= self._critical_threshold:
                        self.context_nearly_full.emit(n_used, n_ctx)
                        warned = True
                    elif usage_ratio >= self._warning_threshold and not warned:
                        self.context_warning.emit(n_used, n_ctx)
                        warned = True
                    elif usage_ratio < self._warning_threshold:
                        warned = False

            except Exception:
                pass  # Server might be temporarily unavailable

            # Sleep in small increments for responsive stopping
            for _ in range(self._poll_interval * 10):
                if not self._running:
                    break
                time.sleep(0.1)


class ChatRunner(QThread):
    """Worker thread that executes the chat completion loop.
    
    Communicates with llama.cpp, parses incoming SSE chunks, intercepts
    tool calls, executes them via McpManager, and feeds results back.
    """

    chunk_received = Signal(str)
    generation_complete = Signal(list)
    error_occurred = Signal(str)
    tool_call_detected = Signal(str, str)  # tool_name, tool_args
    reasoning_chunk_received = Signal(str)
    telemetry_ready = Signal(dict)  # {ttft_s, tps, prompt_tokens, predicted_tokens}
    rag_context_applied = Signal(int)  # number of chunks injected as context

    def __init__(self, messages: list, params: dict, mcp_manager, skills_manager=None, parent=None):
        super().__init__(parent)
        self.messages = list(messages)
        self.params = dict(params)
        self.mcp_manager = mcp_manager
        self.skills_manager = skills_manager
        self.retriever = None
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

    @staticmethod
    def _encode_image(path: str):
        """Return a data: URL for a local image file, or None on failure."""
        import base64
        import mimetypes
        from pathlib import Path
        try:
            p = Path(path)
            if not p.exists():
                return None
            mime, _ = mimetypes.guess_type(str(p))
            if not mime or not mime.startswith("image/"):
                mime = "image/png"
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
        except Exception:
            return None

    def _apply_image_attachments(self):
        """Rewrite the latest user message as an OpenAI multimodal content array
        when image attachments are present (WS5).

        Base64-encoding happens here (Python), never in QML. LlamaClient
        forwards ``messages`` verbatim, so no client change is needed.
        """
        attachments = self.params.get("attachments") or []
        if not attachments:
            return
        idx = None
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                idx = i
                break
        if idx is None:
            return
        msg = self.messages[idx]
        text = msg.get("content")
        if not isinstance(text, str):
            return  # already multimodal or unexpected shape
        content = [{"type": "text", "text": text}]
        for path in attachments:
            data_url = self._encode_image(path)
            if data_url:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url},
                })
        if len(content) > 1:
            msg["content"] = content

    def _latest_user_query(self) -> str:
        """Return the text of the most recent user message, if any."""
        for m in reversed(self.messages):
            if m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Multimodal content: concatenate the text parts (WS5).
                    return " ".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                return ""
        return ""

    def _build_rag_prefix(self, settings, port: int) -> list:
        """Build an optional RAG system-message prefix for the sent messages.

        Runs retrieval and (when enabled) LLM reranking on this worker thread.
        Returns [] when RAG is disabled, no retriever is wired, or nothing is
        found; on any failure it degrades to no context.
        """
        if self.retriever is None or not settings.get_bool("rag/enabled"):
            return []
        query = self._latest_user_query()
        if not query:
            return []
        try:
            rerank_enabled = settings.get_bool("rag/rerank_enabled")
            rerank_top_n = settings.get_int("rag/rerank_top_n") or 20
            results = self.retriever.retrieve_for_chat(
                query,
                top_k=3,
                rerank_enabled=rerank_enabled,
                rerank_top_n=rerank_top_n,
                model=self.params.get("model", "default"),
                port=port,
            )
            texts = [r.get("text", "") for r in results if r.get("text")]
            if texts:
                self.rag_context_applied.emit(len(texts))
                return [{"role": "system",
                         "content": "Relevant context:\n" + "\n\n".join(texts)}]
        except Exception:
            pass
        return []

    def _compose_messages(self, rag_prefix: list) -> list:
        """Return the messages to send, folding any RAG context into the
        leading system message so the request never carries two consecutive
        system messages (some chat templates reject that). self.messages is
        never mutated, so the history returned to QML stays intact.
        """
        if not rag_prefix:
            return self.messages
        msgs = list(self.messages)
        if msgs and msgs[0].get("role") == "system" and isinstance(msgs[0].get("content"), str):
            head = dict(msgs[0])
            head["content"] = rag_prefix[0]["content"] + "\n\n" + head["content"]
            msgs[0] = head
            return msgs
        return rag_prefix + msgs

    def _execute_loop(self):
        settings = AppSettings()
        port = settings.get_int("server/port") or 8080
        client = LlamaClient(port=port)

        # ── Image attachments (WS5): rewrite the latest user message as a
        # multimodal content array before any RAG/query processing.
        self._apply_image_attachments()

        # ── RAG context injection (WS2/WS3) ───────────────────────────
        # Retrieval and optional LLM reranking make blocking calls, so they run
        # here (on this QThread) rather than on the QML/UI thread. The context
        # is prepended only to the messages sent to the model, never to
        # self.messages, so the history returned to QML stays unchanged.
        rag_prefix = self._build_rag_prefix(settings, port)

        max_loops = 10
        loop_count = 0
        finalized = False  # True once a terminal signal has been emitted

        # ── Per-response telemetry (WS1) ──────────────────────────────
        # Wall-clock TTFT is measured from the very first request send to the
        # first content/reasoning chunk of the whole turn. Token counts and
        # tok/s come from the llama-server `timings` object on the final SSE
        # chunk, aggregated across tool-loop iterations for the final answer.
        turn_start = time.monotonic()
        ttft_s = None
        agg_prompt_tokens = 0
        agg_predicted_tokens = 0
        final_tps = None
        saw_timings = False

        def _emit_telemetry():
            self.telemetry_ready.emit({
                "ttft_s": ttft_s,
                "tps": final_tps if saw_timings else None,
                "prompt_tokens": agg_prompt_tokens if saw_timings else None,
                "predicted_tokens": agg_predicted_tokens if saw_timings else None,
            })

        while loop_count < max_loops and not self._is_stopped:
            loop_count += 1

            # On the final permitted iteration, disable tools so the model is
            # forced to produce a text answer instead of requesting yet another
            # tool call. Without this, exhausting the loop while a tool call is
            # still pending would exit without ever emitting a completion
            # signal, leaving the UI stuck in the "generating" state.
            is_last_loop = loop_count >= max_loops

            # Fetch tools from MCP and native skills (excluded in Plan Mode)
            mode = self.params.get("mode", 0)
            if mode == 1 or is_last_loop:  # Plan Mode / final round: no tools
                tools = None
            else:
                tools = []
                if self.mcp_manager:
                    mcp_tools = self.mcp_manager.get_openai_tools()
                    if mcp_tools:
                        tools.extend(mcp_tools)
                if self.skills_manager:
                    skill_tools = self.skills_manager.get_active_tools_schema()
                    if skill_tools:
                        tools.extend(skill_tools)
                if not tools:
                    tools = None

            # Prepare chat completion parameters
            model = self.params.get("model", "default")
            temperature = self.params.get("temperature", 0.7)
            max_tokens = self.params.get("max_tokens", 2048)
            
            extra_params = {
                "top_p": self.params.get("top_p", 0.95),
                "top_k": self.params.get("top_k", 40),
                "repeat_penalty": self.params.get("repeat_penalty", 1.1),
            }

            # Verify the running server is actually serving the requested model.
            # This back-tests the selection: if a different model is loaded, refuse
            # to generate so the user never gets a response from the wrong model.
            if model != "default" and ":" not in model:
                try:
                    models_list = client.models(timeout=2.0)
                    loaded_model = models_list[0].get("id", "") if models_list else ""
                    if model not in loaded_model:
                        self.error_occurred.emit(
                            f"Model mismatch: requested '{model}' but server is "
                            f"currently running '{loaded_model}'. Stopping generation "
                            f"to avoid replying with the wrong model."
                        )
                        finalized = True
                        break
                except Exception:
                    # Server unreachable / no /props endpoint (e.g. cloud-routed).
                    # Proceed to chat_completion, which will surface a real error.
                    pass

            resp = client.chat_completion(
                messages=self._compose_messages(rag_prefix),
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
            full_reasoning = ""
            iter_timings = None  # llama-server timings block for this iteration

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

                        # llama-server reports timings on the final chunk
                        _t = parsed.get("timings")
                        if _t:
                            iter_timings = _t

                        delta = parsed.get("choices", [{}])[0].get("delta", {})
                        
                        # Accumulate content chunks
                        content_chunk = delta.get("content")
                        if content_chunk:
                            if ttft_s is None:
                                ttft_s = time.monotonic() - turn_start
                            full_content += content_chunk
                            self.chunk_received.emit(content_chunk)
                        
                        # Accumulate reasoning content (thinking phase)
                        reasoning_chunk = delta.get("reasoning_content")
                        if reasoning_chunk:
                            if ttft_s is None:
                                ttft_s = time.monotonic() - turn_start
                            full_reasoning += reasoning_chunk
                            self.reasoning_chunk_received.emit(reasoning_chunk)
                        
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

            # Aggregate telemetry from this iteration's timings block
            if iter_timings:
                saw_timings = True
                agg_prompt_tokens += int(iter_timings.get("prompt_n", 0) or 0)
                agg_predicted_tokens += int(iter_timings.get("predicted_n", 0) or 0)
                pps = iter_timings.get("predicted_per_second")
                if pps is not None:
                    final_tps = pps

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
                assistant_msg = {"role": "assistant", "content": full_content or None}
                if full_reasoning:
                    assistant_msg["reasoning_content"] = full_reasoning
                assistant_msg["tool_calls"] = tool_calls_list
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
                    
                    # Route execution to native skills first, then MCP
                    if self.skills_manager and self.skills_manager.has_tool(name):
                        tool_result = self.skills_manager.execute_tool(
                            name, args, cancel_check=lambda: self._is_stopped
                        )
                    elif self.mcp_manager:
                        tool_result = self.mcp_manager.execute_tool(name, args)
                    else:
                        tool_result = f"Error: no handler available to execute '{name}'"
                    
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
                msg = {"role": "assistant"}
                if full_content:
                    msg["content"] = full_content
                if full_reasoning:
                    msg["reasoning_content"] = full_reasoning
                self.messages.append(msg)
                _emit_telemetry()
                self.generation_complete.emit(self.messages)
                finalized = True
                break

        # Safety net: the loop hit its iteration cap while a tool call was still
        # pending (the model never produced a final answer). Emit a completion
        # so the UI is released instead of hanging forever. The tool-less final
        # round above normally prevents reaching this, but a misbehaving model
        # could still return tool calls even when no tools were offered.
        if not finalized and not self._is_stopped:
            _emit_telemetry()
            self.generation_complete.emit(self.messages)


class ChatManager(QObject):
    """Manages chat completion requests and orchestrates ChatRunners.

    Also monitors context usage and can trigger auto-compaction when the
    context window is nearly full.
    """

    chunk_received = Signal(str)
    generation_complete = Signal(list)
    error_occurred = Signal(str)
    tool_call_detected = Signal(str, str)
    reasoning_chunk_received = Signal(str)
    telemetry_ready = Signal(dict)  # {ttft_s, tps, prompt_tokens, predicted_tokens}
    rag_context_applied = Signal(int)  # number of chunks injected as context
    # Auto-compaction signals
    context_nearly_full = Signal(int, int)  # used_tokens, max_tokens
    context_warning = Signal(int, int)  # used_tokens, max_tokens (at 60%)
    auto_compact_triggered = Signal()  # Emitted when auto-compaction starts
    auto_compact_complete = Signal(str)  # Emitted with summary text after compaction
    auto_compact_error = Signal(str)  # Emitted if auto-compaction fails

    def __init__(self, mcp_manager=None, skills_manager=None, retriever=None, parent=None):
        super().__init__(parent)
        self.mcp_manager = mcp_manager
        self.skills_manager = skills_manager
        self.retriever = retriever
        self._runner = None
        self._monitor = None
        self._auto_compact_pending = False

    def start_monitoring(self, port: int):
        """Start the context usage monitor."""
        self.stop_monitoring()
        self._monitor = ContextMonitor(port=port, parent=self)
        self._monitor.context_nearly_full.connect(self._on_context_critical)
        self._monitor.context_warning.connect(self._on_context_warning)
        self._monitor.start()

    def stop_monitoring(self):
        """Stop the context usage monitor."""
        if self._monitor:
            self._monitor.stop()
            self._monitor.wait(2000)
            self._monitor = None

    def _on_context_warning(self, used: int, total: int):
        """Handle context warning (60% full)."""
        self.context_warning.emit(used, total)

    def _on_context_critical(self, used: int, total: int):
        """Handle critical context usage (80% full) - trigger auto-compaction."""
        if not self._auto_compact_pending:
            self._auto_compact_pending = True
            self.context_nearly_full.emit(used, total)
            self.auto_compact_triggered.emit()

    @Slot()
    def acknowledge_auto_compact(self):
        """Called by QML after auto-compaction completes."""
        self._auto_compact_pending = False

    @Slot(list, str)
    def auto_compact(self, messages: list, model_name: str):
        """Summarize conversation to compact context, then clear KV cache.

        This is the server-side auto-compaction method. It takes the current
        conversation history, generates a concise summary via the model, then
        clears the server's KV cache. The summary is emitted via the
        auto_compact_complete signal so QML can update its message history.

        Args:
            messages: Current conversation message history.
            model_name: Model name for the summary request.
        """
        if not messages or len(messages) < 2:
            return

        try:
            settings = AppSettings()
            port = settings.get_int("server/port") or 8080
            client = LlamaClient(port=port)

            # Build summary prompt from conversation history
            # Keep messages compact: serialize to JSON string
            history_text = json.dumps(messages, ensure_ascii=False)

            # Trim if too large for a summary request (keep under ~6K chars)
            if len(history_text) > 6000:
                # Keep first system message + recent messages
                trimmed = []
                for msg in messages:
                    if msg.get("role") == "system" and len(trimmed) == 0:
                        trimmed.append(msg)
                # Add last N messages that fit
                recent = messages[-6:]
                for msg in recent:
                    if msg not in trimmed:
                        trimmed.append(msg)
                history_text = json.dumps(trimmed, ensure_ascii=False)

            summary_messages = [
                {"role": "system", "content": "Summarize the following conversation concisely, preserving key facts, decisions, and context. Output ONLY the summary."},
                {"role": "user", "content": history_text}
            ]

            resp = client.chat_completion(
                messages=summary_messages,
                model=model_name,
                temperature=0.3,
                max_tokens=1024,
                stream=False,
                timeout=30
            )

            summary = ""
            if isinstance(resp, dict):
                choices = resp.get("choices", [])
                if choices:
                    summary = choices[0].get("message", {}).get("content", "")

            if summary:
                # Clear the server's KV cache
                client.clear_kv_cache()
                self.auto_compact_complete.emit(summary)
                self._auto_compact_pending = False
            else:
                self.auto_compact_error.emit("Auto-compaction produced empty summary")

        except Exception as e:
            self.auto_compact_error.emit(f"Auto-compaction failed: {e}")
            self._auto_compact_pending = False

    @Slot(list, dict)
    def send_message(self, messages: list, params: dict):
        """Slot called from QML to launch the chat completions loop."""
        self.stop_generation()

        self._runner = ChatRunner(messages, params, self.mcp_manager, self.skills_manager)
        self._runner.retriever = self.retriever
        self._runner.chunk_received.connect(self.chunk_received)
        self._runner.generation_complete.connect(self._on_generation_complete)
        self._runner.error_occurred.connect(self.error_occurred)
        self._runner.tool_call_detected.connect(self.tool_call_detected)
        self._runner.reasoning_chunk_received.connect(self.reasoning_chunk_received)
        self._runner.telemetry_ready.connect(self.telemetry_ready)
        self._runner.rag_context_applied.connect(self.rag_context_applied)
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
