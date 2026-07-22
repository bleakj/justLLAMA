---
name: justllama-models-server-api
description: How justLLAMA manages the llama-server process and GGUF models, the OpenAI-compatible API surface, cloud provider routing, and the model browser/downloader/profiles/updater.
tags: [llama-server, gguf, openai-api, cloud-providers, model-browser, download, huggingface, updater]
audience: llm
---

# justLLAMA — Models, Server & API

## The local inference server (`server/manager.py`, `ServerManager`)

justLLAMA supervises a single `llama-server` (from llama.cpp) child process:

- **Start/stop lifecycle** from the GUI; the binary path defaults to
  `~/.local/bin/llama-server-cuda` (`server/binary`), listening on port
  `8080` (`server/port`).
- **CLI argument building** (`server/config.py`) from settings:
  `--ctx-size` (default 4096, auto-detected from GGUF metadata), `--n-gpu-layers`
  (default "auto"; VRAM-based auto-calculation for MoE models), `--threads` (-1 = auto),
  `--batch-size` / `--ubatch-size` (512), `--flash-attn` (on), `--mmap` (on), `--mlock` (off),
  `--numa`, plus the model path.
- **Speculative decoding** uses current llama.cpp flags: `--spec-draft-n-max` (default 3),
  `--spec-draft-n-min` (default 0), `--model-draft`, `--gpu-layers-draft`.
- **CUDA support**: NVIDIA GPUs are auto-detected for `--n-gpu-layers`;
  CPU-only operation is possible by lowering GPU layers.
- **VRAM safety**: Auto-detection caps NGL for MoE models (hard cap 24), prevents OOM
  via context size capping based on available VRAM.
- **Health & logs**: exposes `/health`; log-reader threads stream output and are
  always joined on stop so they don't outlive the process.
- **Single active model**: only one GGUF is loaded at a time; changing models
  restarts the server. The chat loop back-tests the loaded model id and refuses
  to answer on mismatch (see `02-chat-modes-and-tools.md`).
- **Model ejection**: The Chat view sidebar includes an "Eject Model" button to stop
  the server and unload the model from memory.

## The REST client (`server/client.py`, `LlamaClient`)

A thin OpenAI-compatible HTTP client used everywhere (chat, council, model
listing). `chat_completion(messages, model, temperature, max_tokens, stream,
tools, **extra)` supports streaming (SSE) and non-streaming; `models()` lists
the loaded model. It targets `http://127.0.0.1:<port>` for local use, but can be
pointed at any `host`/`api_prefix` with an `api_key` for cloud routing.

## Model management

| Component | Role |
|-----------|------|
| `ModelBrowser` (`models/browser.py`) | Scans `models/directory` (default `~/Documents/models`) for GGUF files and extracts metadata for the Model Browser UI. |
| `ModelMetadata` (`models/metadata.py`) | Reads GGUF file metadata (architecture, block count, MoE detection, expert count) for smart defaults. |
| `ModelDownloader` (`models/downloader.py`) | Downloads GGUF models from the **HuggingFace Hub**. |
| `ModelProfiles` (`models/profiles.py`) | Saves/loads per-model configuration presets (sampling + server args). Includes VRAM-based NGL auto-calculation with MoE-aware logic. |
| `Updater` (`server/updater.py`) | Checks llama.cpp releases; can download and build from source. |

## Model loading workflow

When a user clicks "Load" on a model card in the Model Browser:

1. **Pre-load dialog** opens showing auto-detected settings (context size, GPU layers,
   flash attention) based on GGUF metadata and available VRAM.
2. User can review/adjust settings or click "Edit Full Profile" for advanced options.
3. Settings are saved as a per-model profile and the server starts with the effective config.
4. MoE models (Mixtral, Qwen2-MoE, Qwen3-MoE, Gemma4, etc.) receive conservative NGL
   values (max 24) to prevent OOM.
5. Context size is auto-capped based on available VRAM to prevent OOM during generation.

## OpenAI-compatible API surface

Because `llama-server` speaks the OpenAI API, justLLAMA re-exposes it. The
**API view** shows the base URL, model name, and copy-paste snippets. Any
OpenAI-format client works:

```python
import openai
client = openai.OpenAI(base_url="http://localhost:8080/v1", api_key="no-key")
resp = client.chat.completions.create(
    model="your-model-name",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

> Security note: the local API has **no authentication** (`api_key="no-key"`)
> and is intended for `localhost`. Do not expose it to untrusted networks.

## Cloud provider routing (opt-in)

`server/providers.py` defines OpenAI-compatible cloud partners. A model is
routed to the cloud when its identifier uses a **`provider:model`** prefix
(e.g. `nvidia:meta/llama-3.1-70b-instruct`). Used primarily by **Council** slots
and the **Cloud Model Browser** (`ExternalModelsManager` fetches model lists).

| Provider id | Label | Base URL | API prefix |
|-------------|-------|----------|------------|
| `nvidia` | NVIDIA | `https://integrate.api.nvidia.com` | `/v1` |
| `openrouter` | OpenRouter | `https://openrouter.ai/api` | `/v1` |
| `opencode` | Opencode | `https://api.opencode.com` (overridable via `cloud_endpoints/opencode`) | `/v1` |
| `gemini` | Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `` (empty) |
| `kilocode` | Kilocode | `https://api.kilocode.com` | `/v1` |

API keys come from environment variables loaded from `.env`
(`NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `OPENCODE_API_KEY`, `GEMINI_API_KEY`,
`KILOCODE_API_KEY`). A cloud slot with no configured key is skipped, not errored
into a crash.

## Guidance for an operating model

- Assume **one local model at a time**; requesting a different local model
  implies a slow server restart.
- Prefer local inference by default; routing to a cloud provider **sends the
  prompt off-machine** — only do so when the user has explicitly opted in.
- The default 4096-token context is small; keep prompts, RAG, and memory
  injection within budget or expect truncation.
