# justLLAMA

A desktop GUI wrapper for [llama.cpp](https://github.com/ggerganov/llama.cpp) on Linux. Chat with local LLMs, manage models, run RAG over your documents, and expose an OpenAI-compatible API — all from one app.

Built with **PySide6** + **Kirigami** (Qt6/QML) on **Fedora KDE Plasma**.

![License](https://img.shields.io/badge/license-LGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Qt](https://img.shields.io/badge/Qt6-6.11-brightgreen)

---

## What it does

justLLAMA is a local AI workbench. It manages a `llama-server` process, lets you chat with it through a clean GUI, and provides tools for document retrieval (RAG) and persistent memory. Everything runs on your own hardware — no cloud APIs, no data leaving your machine.

### Features

- **Chat** — Streaming conversation with any GGUF model, adjustable generation parameters (temperature, top-p, top-k, repeat penalty, max tokens)
- **4 Chat Modes** — Switch between Chat, Plan, Build, and Council modes. Each mode has distinct color accents (blue, amber, green, purple) visible on the sidebar header, border, and streaming area. The mode persists across sessions.
  - **Plan Mode** — Model performs read-only analysis and outputs structured markdown plans
  - **Build Mode** — Model can create, edit, and read local files via structured build operations; operations queue in a pending panel for review and one-click approval
  - **Council Mode** — Sequentially queries three independently configured models and synthesizes their responses into a single answer
- **Model Browser** — Scan local directories for GGUF files, view model info, download from HuggingFace Hub
- **Model Profiles** — Save and load per-model configuration presets
- **RAG (Retrieval-Augmented Generation)** — Ingest PDFs, DOCX, TXT, and Markdown files; chunk and embed them into a ChromaDB vector store with hybrid search (vector + BM25); relevant context automatically injected during chat
- **Agent Memory** — Short-term (conversation deque) and long-term (SQLite-backed) memory with automatic summarization. Browse and manage memory via a dedicated Memory view
- **Context Compaction** — Summarize and compact long conversations to stay within context window limits
- **API Server** — OpenAI-compatible REST API via llama-server; copy-paste config for Python SDK, curl, environment variables
- **Server Management** — Start/stop llama-server from the GUI, configure GPU layers, context size, threads, and all CLI options
- **CUDA Support** — Automatic GPU detection and `--n-gpu-layers` configuration for NVIDIA cards
- **Update Checker** — Check for llama.cpp releases, download and build from source
- **Error Toast** — Non-blocking in-app notification system for errors and operation results

---

## Requirements

- **OS:** Fedora 40+ (KDE Plasma) or similar Linux distro
- **Python:** 3.11+
- **GPU:** NVIDIA GPU with CUDA drivers (recommended) or CPU-only
- **llama-server:** Pre-installed binary (e.g., from Fedora repos or built from source)

### System packages

```bash
# Fedora
sudo dnf install python3-pyside6 qt6-qtdeclarative qt6-qtmultimedia \
    kirigami2-devel exiv2-devel
```

---

## Installation

### From source

```bash
git clone https://github.com/youruser/justllama.git
cd justllama

# Create venv (with system-site-packages for PySide6 QML path)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# Install
pip install -e .

# With RAG support
pip install -e ".[rag]"
```

### Run

```bash
justllama
# or
python3 -m justllama
```

---

## Usage

### 1. Select a model

Go to the **Models** tab. Point the model directory to your GGUF files (default: `~/Documents/models/`). Click a model to select it for chat.

### 2. Start the server

Go to **Settings**, configure your preferences (GPU layers, context size, threads), and click **Start Server**. The status bar turns green when ready.

### 3. Chat

Switch to **Chat** and start typing. Expand **▸ Generation** above the input to tune temperature, top-p, top-k, and other parameters.

Use the mode selector ComboBox (above the input) to switch modes:
- **Chat** — Standard conversational assistant
- **Plan** — Read-only analysis; model outputs detailed markdown plans
- **Build** — Model can create/edit files; operations appear in the sidebar for review before applying
- **Council** — Queries three different models sequentially and synthesizes their responses

### 4. Use RAG

Go to **RAG**, enable it, and upload documents. They'll be chunked and embedded into the vector store. Relevant context is automatically injected into chat when you ask about your documents.

### 5. Use the API

Go to **API** to see the OpenAI-compatible endpoint configuration. Copy the base URL, model name, and paste them into any tool that supports OpenAI's API format:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="no-key"
)

response = client.chat.completions.create(
    model="your-model-name",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

## Configuration

justLLAMA stores settings via Qt's `QSettings` (typically `~/.config/justllama/justllama.conf`). Key settings:

### Server

| Setting | Default | Description |
|---------|---------|-------------|
| `server/binary` | `llama-server` | Path to llama-server binary |
| `server/port` | `8080` | Server listen port |
| `server/ctx_size` | `32768` | Context window size |
| `server/n_gpu_layers` | `99` | GPU layers to offload (-1 = auto) |
| `server/threads` | `0` | CPU threads (0 = auto) |
| `server/model_path` | — | Active model file path |

### Models

| Setting | Default | Description |
|---------|---------|-------------|
| `models/directory` | `~/Documents/models` | Model search directory |

### RAG

| Setting | Default | Description |
|---------|---------|-------------|
| `rag/enabled` | `false` | Enable RAG pipeline |
| `rag/chunk_size` | `512` | Document chunk size |
| `rag/chunk_overlap` | `64` | Chunk overlap |
| `rag/vectorstore_path` | — | Vector store directory |

### Memory

| Setting | Default | Description |
|---------|---------|-------------|
| `memory/enabled` | `false` | Enable agent memory |
| `memory/db_path` | `:memory:` | Long-term memory database |
| `memory/max_short_term` | `50` | Short-term message limit |

### Council

| Setting | Default | Description |
|---------|---------|-------------|
| `council/model_1` | — | First council model path |
| `council/model_2` | — | Second council model path |
| `council/model_3` | — | Third council model path |

### Chat

| Setting | Default | Description |
|---------|---------|-------------|
| `chat/mode` | `chat` | Active chat mode (`chat`, `plan`, `build`, `council`) |

---

## Project structure

```
justllama/
├── main.py                 # Entry point: QGuiApplication + QML engine
├── __main__.py             # `python -m justllama` support
├── config/
│   └── settings.py         # QSettings wrapper
├── server/
│   ├── manager.py          # llama-server process lifecycle
│   ├── client.py           # REST API client
│   ├── config.py           # CLI argument builder
│   ├── council.py          # Council Mode orchestrator (multi-model synthesis)
│   ├── build.py            # Build Manager (file read/write/edit for Build mode)
│   └── updater.py          # Update checker/downloader/builder
├── models/
│   ├── browser.py          # GGUF file scanner + metadata extractor
│   ├── downloader.py       # HuggingFace Hub download
│   └── profiles.py         # Per-model config profiles
├── rag/
│   ├── ingestion.py        # Document chunking pipeline
│   ├── vectorstore.py      # ChromaDB vector store
│   └── retriever.py        # Hybrid search (vector + BM25)
├── memory/
│   ├── short_term.py       # Conversation context (deque)
│   ├── long_term.py        # SQLite-backed persistent memory
│   └── manager.py          # Memory orchestrator + summarization
└── ui/qml/
    ├── Main.qml             # Application shell + navigation stack
    ├── ChatView.qml         # Chat interface, 4 modes, streaming, generation controls
    ├── ModelBrowser.qml     # Model selection + download from HuggingFace
    ├── SettingsView.qml     # Server config, update checker, council model config
    ├── RAGView.qml          # Document management + ingestion
    ├── MemoryView.qml       # Memory browser (short/long term)
    ├── APIView.qml          # API reference + copy-paste code snippets
    ├── ConfigSnippet.qml    # Reusable code snippet component
    └── ErrorToast.qml       # Non-blocking notification overlay
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[rag,dev]"

# Run tests (288 tests)
python3 -m pytest tests/ -v

# Quick check
python3 -m pytest tests/ -q
```

### Architecture

- **Python** handles all business logic: server management, API calls, file I/O, RAG pipeline, memory, council orchestration, build operations
- **QML/Kirigami** handles the UI: layout, navigation, animations, theme integration, per-mode color theming
- Communication is via Qt context properties and signal/slot connections
- No Python imports in QML; no direct QML manipulation from Python (except context properties)
- Council and Build modes use QThread workers to avoid blocking the UI during model switching and file operations
- Chat modes use reactive QML bindings for instant visual feedback on mode switches

---

## License

LGPL-3.0 — compatible with llama.cpp (MIT) and PySide6 (LGPL).

---

## Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — the inference engine this wraps
- [Kirigami](https://community.kde.org/Kirigami) — KDE's cross-platform UI framework
- [PySide6](https://wiki.qt.io/Qt_for_Python) — official Python bindings for Qt6
