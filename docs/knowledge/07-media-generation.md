---
name: justllama-media-generation
description: How justLLAMA generates images and video via a managed ComfyUI subprocess using GGUF Flux (image) and LTX/WAN (video) workflows, plus the agentic ComfyUI skill.
tags: [image-generation, video-generation, comfyui, flux, ltx, wan, gguf, workflows]
audience: llm
---

# justLLAMA — Image & Video Generation

justLLAMA generates media by driving **ComfyUI** as a managed backend. This is
optional and requires ComfyUI installed (default `~/.config/comfy-cli/ComfyUI`)
with the `ComfyUI-GGUF` custom node and appropriate models/VAEs.

## Shared ComfyUI lifecycle (`server/comfy_helpers.py`)

- ComfyUI is launched **as a subprocess** and managed via a QThread worker with
  **health-check polling** until it is ready to accept jobs.
- The image and video generators **share** the same ComfyUI instance.
- On app shutdown there is no long-lived generation subprocess to kill; an
  in-flight generation thread is GC-collected.

## Image generation (`server/imagegen.py`, `ImageGenManager`)

- Uses GGUF-powered **Flux** models scanned from `~/Documents/models/image/`.
- Workflow template: `server/flux_workflow.json` (ComfyUI API format).
- Flow: pick a Flux GGUF model → enter a prompt → **Generate**. ComfyUI is
  launched automatically; results appear in a gallery in the **Images** view.

## Video generation (`server/videogen.py`, `VideoGenManager`)

- Scans `~/Documents/models/video/` and supports multiple architectures:
  **LTX** (`ltx_workflow.json`) and **WAN** (`wan_workflow.json`), among others.
- Same flow as images, in the **Videos** view. Video generation can take
  **several minutes**.
- Requires video GGUF models symlinked into ComfyUI's
  `models/diffusion_models/` and matching VAEs in `models/vae/`.

## The agentic ComfyUI skill (`comfy_agent`)

Beyond the fixed UI templates, the **`comfy_agent` native skill** lets a chat
model **author its own ComfyUI API-format workflow**, execute it, and read back
the exact ComfyUI error trace for autonomous debugging. It pairs with
`get_comfyui_knowledge`, which serves four bundled guides in
`server/skills/comfy_knowledge/`:

- `comfyui-core.md` — workflow JSON (API) format, node/data types, standard
  pipelines (txt2img/img2img/upscale/inpaint), KSampler params, common mistakes.
- `model-compatibility.md` — which models/VAEs pair with which architectures.
- `prompt-engineering.md` — prompting guidance for diffusion models.
- `troubleshooting.md` — recovery from OOM, stalls, and ComfyUI crashes.

The skill's timeout is raised to **360s** because generation is slow.

## Key facts about ComfyUI workflows (for a model authoring them)

- Workflows are JSON mapping **string node IDs** → `{class_type, inputs, _meta}`.
- Connections are `["sourceNodeId", outputIndex]` (string id, integer index).
- **API format** is for execution; **Web UI format** (`{nodes, links}`) is for
  saving/editing in the canvas — don't confuse them.
- `CheckpointLoaderSimple` outputs `MODEL(0)`, `CLIP(1)`, `VAE(2)`.
- Registered QML views: `ImageView.qml` (as `ImageGenView`), `VideoView.qml`
  (as `VideoGenView`).

## Guidance for an operating model

- Generation is **resource-intensive** (GPU/VRAM) and slow; set expectations and
  respect long timeouts rather than retrying prematurely.
- If a required model is missing, prefer downloading it via ComfyUI's model
  tools rather than asking the user to fetch it manually (see `comfyui-core.md`).
- Do not spin up parallel heavy jobs that would exhaust VRAM; check system stats
  and queue state first.
