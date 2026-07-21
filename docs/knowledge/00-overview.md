---
name: justllama-overview
description: What justLLAMA is, its purpose, design philosophy, capability surface, and the implications (privacy, trust, safety) of operating it. Read this first.
tags: [overview, purpose, philosophy, privacy, local-first, workbench]
audience: llm
---

# justLLAMA — Overview

## One-sentence definition

justLLAMA is a **local-first desktop AI workbench** for Linux that began as a
GUI wrapper around [`llama.cpp`](https://github.com/ggerganov/llama.cpp)'s
`llama-server` and grew into an integrated environment for chatting with local
LLMs, running Retrieval-Augmented Generation (RAG), persistent agent memory,
tool use via Model Context Protocol (MCP) and native skills, image/video
generation via ComfyUI, and an OpenAI-compatible API — all coordinated from one
Qt6/QML application.

## Why it exists (purpose)

The core idea is to give a single desktop user **full ownership of an AI stack**
without depending on a cloud service. `llama.cpp` provides fast local inference
for GGUF-quantized models; justLLAMA wraps that inference engine with the
surrounding capabilities a modern "AI assistant" needs — memory, retrieval,
tools, multimodal generation, and an agentic chat loop — so everything runs on
the user's own hardware by default.

It is built with **PySide6 + Kirigami (Qt6/QML)** and targets **Fedora / KDE
Plasma** (Linux 40+), typically with an NVIDIA CUDA GPU but with CPU-only
fallback.

## What it can do (capability surface)

| Capability | Summary |
|------------|---------|
| Chat | Streaming conversation with any local GGUF model; adjustable sampling params; supports reasoning/thinking output and tool calls. |
| 4 Chat Modes | **Chat** (assistant), **Plan** (read-only analysis, no tools), **Build** (file create/edit/read + shell), **Council** (multi-model synthesis). |
| RAG | Ingest PDF/DOCX/TXT/MD/RST → chunk → embed into ChromaDB → hybrid retrieval (vector + BM25) injected into chat. |
| Agent Memory | Short-term deque + long-term SQLite (FTS) memory, browsable and clearable. |
| Native Skills | In-process Python "skills" exposed as OpenAI tools (terminal, time, ComfyUI agent, Context7, user-authored). |
| MCP | Connect external MCP tool servers (stdio) whose tools become callable in chat. |
| Image/Video Gen | ComfyUI subprocess driven by GGUF Flux (image) and LTX/WAN (video) workflows. |
| Model management | Scan local GGUF dirs, read metadata, download from HuggingFace, save per-model profiles. |
| Cloud (opt-in) | Council slots and model browsing can use NVIDIA, OpenRouter, Opencode, etc. via API keys. |
| API server | Exposes llama-server's OpenAI-compatible REST endpoint with copy-paste client snippets. |
| Voice input | Optional local speech-to-text (whisper.cpp) for dictating chat input. |

## Design philosophy

1. **Local-first, cloud-optional.** No data leaves the machine unless the user
   explicitly configures a cloud provider API key and routes a request to it.
2. **Separation of concerns.** All business logic lives in Python; QML/Kirigami
   only handles presentation. Communication is via Qt context properties and
   signals/slots — no Python imports in QML and no direct QML manipulation from
   Python beyond context properties.
3. **Non-blocking UI.** Long operations (chat generation, council model
   swapping, file ops, ComfyUI, MCP async I/O) run on `QThread` workers or a
   background asyncio loop so the GUI never freezes.
4. **Graceful degradation.** Optional dependencies (chromadb, sentence-
   transformers, rank_bm25, pymupdf, python-docx, pywhispercpp) are lazily
   imported; features fall back or disable cleanly when a dependency is absent
   (e.g. RAG retrieval falls back from vector search → BM25 → substring match).
5. **Extensibility.** Users can drop custom Python skills into a skills folder
   and connect arbitrary MCP servers without editing core code.

## Implications an operating LLM must understand

This is the most important section for another model reasoning about the tool.

- **It has real side effects on the host.** Build mode and the terminal skill
  can **write files and execute arbitrary shell commands** in the user's working
  directory. MCP servers and downloads run external processes. Treat these as
  privileged actions: prefer read-first, confirm destructive operations, and
  never fabricate success.
- **It is single-user and desktop-scoped.** There is no auth layer; the
  OpenAI-compatible API defaults to `http://localhost:8080` with `api_key="no-key"`.
  It is not hardened for multi-tenant or public exposure.
- **Secrets live in `.env`.** Cloud API keys are stored in a gitignored
  `justllama/.env`, never in QSettings. Do not echo, log, or transmit them.
- **Only one model is loaded at a time** by the local server. Switching models
  (including every Council run) stops and restarts `llama-server`, which is slow
  and disrupts any in-flight generation. The chat loop back-tests the loaded
  model and refuses to answer if the running model doesn't match the request.
- **Context is finite.** Default context window is 4096 tokens; RAG and memory
  injection consume that budget. Long conversations are protected automatically:
  the chat auto-compacts (summarizes prior turns) when usage crosses ~85%, and a
  hard sliding-window trim guarantees every request fits the window, dropping the
  oldest messages if needed. Manual compaction remains available via the button.
- **Generation can take minutes** (especially video); tool timeouts are raised
  accordingly (skills default 30s, ComfyUI agent 360s, terminal 120s).

## Where to read next

- Architecture & threading model → `01-architecture.md`
- Chat modes and the agentic tool loop → `02-chat-modes-and-tools.md`
- RAG → `03-rag-pipeline.md`; Memory → `04-memory.md`
- Skills & MCP → `05-skills-and-mcp.md`
- Models, server & API → `06-models-server-api.md`
- Image/Video → `07-media-generation.md`
- Settings & security → `08-configuration-and-security.md`
