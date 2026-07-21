---
name: justllama-configuration-and-security
description: justLLAMA's configuration model (QSettings keys with defaults, .env secrets) and a consolidated security/trust/safety analysis for models and integrators.
tags: [configuration, settings, qsettings, env, secrets, security, safety, trust]
audience: llm
---

# justLLAMA — Configuration & Security

## Two configuration stores

1. **QSettings** (non-secret config): `~/.config/justllama/justllama.conf`,
   wrapped by `AppSettings` (`config/settings.py`) with typed getters/setters and
   a `settings_changed(key, value)` signal that live-reconnects dependent
   subsystems (e.g. MCP reconnects when `mcp/servers` changes).
2. **`.env` secrets** (`config/env.py`): cloud API keys live **only** in
   `justllama/.env` (gitignored), loaded via `python-dotenv` at startup with
   `override=False` (real env vars win). The Settings UI writes keys here via
   `set_api_key`; they are **never** placed in QSettings.

### Key QSettings defaults

| Key | Default | Meaning |
|-----|---------|---------|
| `server/binary` | `~/.local/bin/llama-server-cuda` | llama-server path |
| `server/port` | `8080` | listen port |
| `server/ctx_size` | `4096` | context window |
| `server/n_gpu_layers` | `99` | GPU offload layers |
| `server/threads` | `-1` | CPU threads (auto) |
| `server/batch_size` / `server/ubatch_size` | `512` | batch sizes |
| `server/flash_attn` / `server/mmap` / `server/mlock` | on / on / off | perf flags |
| `models/directory` | `~/Documents/models` | GGUF scan dir |
| `rag/enabled` | `false` | RAG on/off |
| `rag/chunk_size` / `rag/chunk_overlap` | `512` / `50` | chunking |
| `rag/vectorstore_path` | `~/.local/share/justllama/vectordb` | ChromaDB path |
| `memory/enabled` | `false` | memory on/off |
| `memory/db_path` | `~/.local/share/justllama/memory.db` | long-term DB |
| `memory/max_short_term` | `50` | short-term window |
| `chat/mode` | `chat` | active mode |
| `council/model_1..3` | `""` | council slots |
| `skills/<id>_enabled` | (unset→false) | per-skill toggle |
| `skills/user_directory` | `~/.local/share/justllama/skills` | user skills dir |
| `mcp/servers` | `[]` | enabled MCP commands |
| `mcp/servers_config` | (JSON) | full MCP server objects |
| `cloud_endpoints/opencode` | `https://api.opencode.com` | Opencode base URL override |
| `chat/voice_input_enabled` / `chat/voice_model` | `false` / `base.en` | voice input |

### Secret env vars (from `.env`)
`NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `OPENCODE_API_KEY`, `GEMINI_API_KEY`,
`KILOCODE_API_KEY`.

## Security & trust model (read carefully)

justLLAMA is a **single-user desktop tool with real host authority**. An
operating or integrating model must respect these properties:

### Capabilities with host side effects
- **Build mode** (`buildManager`) can create/overwrite/edit files and run shell
  commands (`shell=True`, 60s timeout) in the working directory.
- **Terminal skill** runs arbitrary commands in a persistent shared shell
  (`terminal_manager`) and can send raw keystrokes/control chars.
- **MCP servers** are launched from user-provided shell commands and may do
  anything the user's account can (e.g. filesystem, browser automation).
- **Model/ComfyUI downloads** fetch and execute/load remote artifacts.
- **ComfyUI agent** drives GPU generation subprocesses.

Treat all of the above as privileged: prefer read-before-write, confirm
destructive or irreversible actions, make minimal changes, and **report actual
returned status** (`OK`/`NOT_FOUND`/`ERROR`, exit codes) — never fabricate
success.

### Data boundaries
- **Default is local.** Chat, RAG, and memory stay on-device. Data leaves the
  machine **only** when a `provider:model` cloud route is used (Council slot or
  API routing) — that transmits the prompt to a third party.
- **Secrets**: never echo, log, store in memory/RAG, or transmit API keys. They
  belong solely in `.env`.
- **No auth on the local API.** `http://localhost:8080` with `api_key="no-key"`
  is not hardened; it must not be exposed to untrusted networks.

### Reliability / correctness guards already in place
- Chat loop **back-tests the loaded model** and refuses to answer on mismatch.
- Tool loop is bounded (`max_loops=10`); skills run with timeouts on a worker.
- Council only synthesizes when a real answer exists; otherwise it errors.
- Optional deps degrade gracefully (RAG vector→BM25→substring; missing chromadb
  emits a clear status).

### Guidance summary for another LLM
1. Prefer local, read-only actions; escalate to mutation/cloud only with intent.
2. Keep prompt + RAG + memory within the (small, default 4096) context budget.
3. Expect slow operations (model swap, ComfyUI, downloads); respect timeouts.
4. Be honest about outcomes and never leak secrets.
