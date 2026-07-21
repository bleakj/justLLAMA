---
name: justllama-knowledge-index
description: Index and reading guide for the justLLAMA RAG knowledge base. Explains what justLLAMA is in one paragraph and maps every question type to the document that answers it.
tags: [index, toc, retrieval-guide, justllama, meta]
audience: llm
---

# justLLAMA Knowledge Base — Index

This directory is a **RAG-ready knowledge pack** describing the justLLAMA
application so that another LLM can understand its purpose, architecture, and
operating implications. Each file has YAML frontmatter (`name`, `description`,
`tags`) and is scoped to one topic for clean chunk-level retrieval. The files
are plain Markdown and can be ingested directly by justLLAMA's own RAG pipeline
(`.md` is a supported extension).

## What justLLAMA is (30-second version)

justLLAMA is a **local-first desktop AI workbench** for Linux (Fedora/KDE,
PySide6 + Kirigami). It started as a GUI wrapper around llama.cpp's
`llama-server` and now integrates chat (with Chat/Plan/Build/Council modes),
RAG over local documents, short/long-term agent memory, tool use via native
Python "skills" and MCP servers, image/video generation via ComfyUI, an
OpenAI-compatible API, and optional cloud model routing. Everything runs on the
user's hardware by default; data leaves the machine only when a cloud provider
is explicitly configured and used.

## Document map

| # | File | Answers questions like… |
|---|------|--------------------------|
| 00 | `00-overview.md` | What is justLLAMA? Why does it exist? What are the risks/implications of using it? |
| 01 | `01-architecture.md` | How is it built? Python vs QML? What manager objects exist? How is concurrency handled? |
| 02 | `02-chat-modes-and-tools.md` | What are Chat/Plan/Build/Council modes? How does the streaming tool-calling loop work? |
| 03 | `03-rag-pipeline.md` | How does RAG ingest/chunk/embed/retrieve? What file types? What fallbacks? |
| 04 | `04-memory.md` | How do short-term and long-term memory work? What is stored where? |
| 05 | `05-skills-and-mcp.md` | How are tools provided? Native skills vs MCP servers? Which are bundled? |
| 06 | `06-models-server-api.md` | How is llama-server managed? Model browsing/download? The OpenAI API? Cloud providers? |
| 07 | `07-media-generation.md` | How are images/video generated via ComfyUI (Flux/LTX/WAN)? |
| 08 | `08-configuration-and-security.md` | What settings/keys exist? Where are secrets? What is the security/trust model? |

## Suggested reading order

Start with **00 (overview)** and **08 (security)** to grasp purpose and the
trust model, then **01 (architecture)** for the mental model, then dive into the
subsystem docs (02–07) as questions require.

## The single most important takeaway for an operating model

justLLAMA is **local and private by default but genuinely powerful**: Build
mode, the terminal skill, and MCP servers can write files and run arbitrary
shell commands on the host; cloud routing can send prompts off-machine.
Prefer local read-only actions, confirm destructive/irreversible operations,
keep within the small default context window, respect long operation timeouts,
report real outcomes, and never leak `.env` secrets.
