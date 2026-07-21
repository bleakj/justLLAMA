---
name: justllama-chat-modes-and-tools
description: The four chat modes (Chat, Plan, Build, Council), how the streaming chat loop works, and how tool calling (MCP + native skills) is orchestrated, including safety-relevant behaviors.
tags: [chat, modes, plan, build, council, tool-calling, agentic-loop, streaming]
audience: llm
---

# justLLAMA — Chat Modes & Tool Calling

## The four chat modes

The active mode is stored in `chat/mode` (`chat`, `plan`, `build`, `council`)
and persists across sessions. Each mode has a distinct color accent in the UI
(blue / amber / green / purple). Numerically, `ChatRunner` receives a `mode`
integer in `params` where `1` == Plan mode (used to suppress tools).

### 1. Chat (standard)
A normal streaming conversational assistant. Tools (MCP + enabled native
skills) are available. Sampling params are user-adjustable: `temperature`,
`top_p` (default 0.95), `top_k` (default 40), `repeat_penalty` (default 1.1),
`max_tokens` (default 2048).

### 2. Plan (read-only analysis)
The model performs **read-only** analysis and emits a structured markdown plan.
Critically, **tools are disabled in Plan mode** — `ChatRunner` sets
`tools = None` when `mode == 1`, so the model cannot invoke MCP tools or native
skills and cannot mutate anything. Use Plan mode to reason about an approach
before executing it.

### 3. Build (file & shell operations)
The model may create, edit, and read local files and run shell commands via
`BuildManager` (exposed as `buildManager`). Operations are expressed as
structured `BUILD_OP` JSON and queued in a pending panel for **human review and
one-click approval** before applying. Supported operation types:

| `op` | Action | Method | Returns |
|------|--------|--------|---------|
| `write` | Create/overwrite a file | `write_file(path, content)` | `OK` / `ERROR: …` |
| `edit` | Single find-and-replace | `edit_file(path, old, new)` | `OK` / `NOT_FOUND` / `ERROR: …` |
| `read` | Read a file | `read_file(path)` | contents / `ERROR: …` |
| `run` | Shell command | `run_command(command)` | stdout+stderr+exit code |

Build operations run in a configurable working directory (`set_work_dir`,
defaults to the CWD justLLAMA was launched from). `run_command` uses
`shell=True` with a **60-second timeout**. **This is a privileged, host-
mutating capability** — an operating model should read before writing, make
minimal edits, and never claim success it did not verify from the returned
status string.

### 4. Council (multi-model synthesis)
Council mode sequentially queries **three independently configured models**
(`council/model_1..3`) with the same prompt, then asks the **main/synthesizer
model** to compare them and produce one unified answer. Orchestrated by
`CouncilRunner` (a QThread) — see `02`/`council` details:

- Each slot may be a **local GGUF path** or a **cloud model** using a
  `provider:model` prefix (`nvidia:`, `openrouter:`, `opencode:`, …). Cloud
  slots read their API key from `.env` via `AppSettings.get_api_key`.
- For **local** slots, the runner **stops the current server, starts
  `llama-server` with that model, waits for `/health` (up to ~30s), queries it
  non-streaming (`max_tokens=1024`)**, then moves on. This model-swapping makes
  Council slow and disruptive to any running session.
- Cloud slots are queried directly over HTTP without touching the local server.
- Synthesis only runs if **at least one** slot returned a real answer
  (placeholder/error responses are filtered out); otherwise it emits an error.
- Afterward it **restores the main model** and emits `synthesis_ready` with the
  synthesis prompt for the main model to answer.

## The streaming chat + tool loop (`ChatRunner`)

`server/chat_manager.py` implements the agentic loop. Key behaviors:

1. **Tool assembly.** Unless in Plan mode, it merges OpenAI tool schemas from
   `mcpManager.get_openai_tools()` and `skillsManager.get_active_tools_schema()`.
   If empty, `tools=None`.
2. **Model back-testing.** For local (non-`provider:`) models it calls
   `client.models()` and, if the requested model id is not part of the loaded
   model id, it **aborts with a "Model mismatch" error** rather than answering
   from the wrong model. If the server is unreachable/cloud-routed it proceeds
   and lets a real error surface.
3. **Streaming parse.** Server-Sent Events are read line-by-line:
   - `delta.content` → accumulated and emitted via `chunk_received`.
   - `delta.reasoning_content` → accumulated and emitted via
     `reasoning_chunk_received` (thinking/reasoning display).
   - `delta.tool_calls` → accumulated by `index` (id, name, streamed argument
     fragments concatenated).
4. **Tool execution.** After the stream ends, if tool calls were requested:
   - The assistant message (with `tool_calls`) is appended to history.
   - Each call is dispatched **native-skills-first** (`skillsManager.has_tool`
     → `execute_tool`), otherwise to `mcpManager.execute_tool`. Results are
     appended as `role: "tool"` messages keyed by `tool_call_id`.
   - The loop repeats so the model can consume tool output. It is bounded to
     **`max_loops = 10`** iterations to prevent infinite tool loops.
5. **Completion.** When a turn produces no tool calls, the assistant message is
   finalized and `generation_complete(messages)` fires.
6. **Cancellation.** `stop_generation()` sets a stop flag and closes the
   in-flight HTTP response; a new `send_message` first stops any running runner.

## Signals emitted (for UI / observers)

`chunk_received(str)`, `reasoning_chunk_received(str)`,
`tool_call_detected(name, args_json)`, `generation_complete(list)`,
`error_occurred(str)`.

## Practical guidance for an operating model

- In **Plan** mode, do not attempt tool use; produce the plan only.
- In **Build** mode, express changes as reviewable `BUILD_OP`s; check returned
  status (`OK`/`NOT_FOUND`/`ERROR`) and report faithfully.
- Long tool runs are expected (ComfyUI, terminal); respect timeouts and poll
  cancellation where the skill supports it.
- If you receive a "Model mismatch" error, the wrong model is loaded — the fix
  is to load the requested model via the server/model selection, not to retry.
