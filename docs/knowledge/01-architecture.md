---
name: justllama-architecture
description: How justLLAMA is structured — the Python/QML split, the entry point and context-property wiring, the manager components, and the concurrency/threading model.
tags: [architecture, threading, qml, pyside6, managers, data-flow]
audience: llm
---

# justLLAMA — Architecture

## High-level shape

justLLAMA is a **Qt6 application** with a strict two-layer split:

- **Python** owns *all* business logic: server process management, HTTP calls,
  file I/O, RAG, memory, council orchestration, build operations, MCP sessions,
  native skills, ComfyUI lifecycle, cloud provider access.
- **QML / Kirigami** owns *only* presentation: layout, navigation (an 8+ tab
  shell), animations, theme, and per-mode color accents.

The two layers communicate exclusively through Qt: Python "manager" objects are
exposed to QML as **context properties**, QML calls their `@Slot` methods, and
Python pushes updates back via **Signals**. There are no Python imports in QML
and no direct QML manipulation from Python beyond setting context properties.

## Entry point and wiring

`justllama/main.py` (`main()`) is the entry point (also reachable via
`python -m justllama` and the `justllama` console script). It:

1. Creates the `QGuiApplication`, sets the Kirigami/`org.kde.desktop` style, and
   sets org/app name to `justllama` (this determines the QSettings path).
2. Calls `load_env()` **before any key reads** so `.env` secrets populate
   `os.environ`.
3. Instantiates every manager (see table below).
4. Registers image/video managers into a small `generation_registry` so the
   ComfyUI native skill can reach them without a circular import.
5. Connects `app.aboutToQuit` to a `_shutdown()` that stops the server, closes
   the long-term memory DB, unloads the voice model, and shuts down MCP, skills,
   and terminal managers cleanly.
6. Loads `ui/qml/Main.qml` after setting each manager as a context property.

## Manager components (Python → QML context property)

| Context property | Class (file) | Responsibility |
|------------------|--------------|----------------|
| `appSettings` | `AppSettings` (config/settings.py) | QSettings wrapper + typed accessors, defaults, API-key bridge. |
| `serverManager` | `ServerManager` (server/manager.py) | llama-server process lifecycle (start/stop/health/logs). |
| `modelBrowser` | `ModelBrowser` (models/browser.py) | Scan GGUF dirs + extract metadata. |
| `downloader` | `ModelDownloader` (models/downloader.py) | HuggingFace Hub downloads. |
| `modelProfiles` | `ModelProfiles` (models/profiles.py) | Per-model config presets. |
| `vectorStore` | `VectorStore` (rag/vectorstore.py) | ChromaDB collection + ingestion. |
| `retriever` | `Retriever` (rag/retriever.py) | Hybrid vector + BM25 search. |
| `memoryManager` | `MemoryManager` (memory/manager.py) | Short/long-term memory orchestration. |
| `chatManager` | `ChatManager` (server/chat_manager.py) | Runs the streaming chat + tool loop on a worker thread. |
| `councilManager` | `CouncilManager` (server/council.py) | Sequential multi-model synthesis. |
| `buildManager` | `BuildManager` (server/build.py) | File read/write/edit + shell for Build mode. |
| `mcpManager` | `McpManager` (server/mcp.py) | MCP stdio sessions on a background asyncio loop. |
| `skillsManager` | `SkillsManager` (server/skills/manager.py) | Discovers/executes native skills. |
| `imageGenManager` / `videoGenManager` | (server/imagegen.py, videogen.py) | ComfyUI-backed generation. |
| `voiceInputManager` | `VoiceInputManager` (voice/manager.py) | whisper.cpp speech-to-text. |
| `externalModels` | `ExternalModelsManager` (server/external_models.py) | Fetch cloud provider model lists. |
| `updater` | `Updater` (server/updater.py) | Check/download/build llama.cpp releases. |
| `terminalManager` | singleton (server/terminal_manager.py) | Persistent PTY shared by the terminal skill. |

## Concurrency / threading model

The UI thread must never block. Concurrency is handled three ways:

1. **`QThread` workers** for bounded long tasks:
   - `ChatRunner` (chat_manager.py) runs the streaming completion + tool loop.
   - `CouncilRunner` (council.py) serializes stop → start → health-check →
     query across three models, then restores the main model.
   - ImageGen/VideoGen use a QThread worker with health-check polling of the
     ComfyUI subprocess.
   Workers communicate results back exclusively via Signals.

2. **A background asyncio event loop in a daemon thread** for MCP. `McpManager`
   spins up `asyncio.new_event_loop()` in a thread; synchronous Qt slots
   dispatch coroutines with `asyncio.run_coroutine_threadsafe(...)` and block on
   the future with a timeout. This is required because the `mcp` client is async
   (stdio transports, `ClientSession`).

3. **A `ThreadPoolExecutor`** inside `SkillsManager` (single worker) to run each
   native skill with a per-skill timeout so a hung tool cannot wedge the chat
   loop.

## Data-flow example: one chat turn with a tool call

1. QML calls `chatManager.send_message(messages, params)`.
2. `ChatManager` spawns a `ChatRunner` (QThread) and connects its signals.
3. `ChatRunner._execute_loop()` gathers tool schemas from `mcpManager` +
   `skillsManager` (unless Plan mode), verifies the loaded model matches the
   request, then streams `chat_completion(..., stream=True, tools=...)` from
   `LlamaClient`.
4. SSE chunks are parsed: `content` → `chunk_received`, `reasoning_content` →
   `reasoning_chunk_received`, and `tool_calls` accumulate by index.
5. If tool calls were requested, each is routed **skills-first, then MCP**,
   executed, and the results appended as `role: "tool"` messages; the loop
   repeats (max 10 iterations) so the model can use the results.
6. When no tool calls remain, the assistant message is finalized and
   `generation_complete` fires with the full message list.

## Persistence locations

- **QSettings** (most config): `~/.config/justllama/justllama.conf`.
- **Secrets**: `justllama/.env` (gitignored; loaded via python-dotenv).
- **Vector DB**: `~/.local/share/justllama/vectordb`.
- **Long-term memory**: `~/.local/share/justllama/memory.db`.
- **User skills**: `~/.local/share/justllama/skills/`.
- **Models (default)**: `~/Documents/models/` (with `image/` and `video/` subdirs).
