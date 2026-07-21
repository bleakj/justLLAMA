---
name: justllama-skills-and-mcp
description: The two tool-provision systems in justLLAMA — in-process native "agent skills" (including user-authored ones) and external MCP tool servers — how they are discovered, exposed, and executed.
tags: [skills, mcp, tools, function-calling, terminal, comfy-agent, extensibility]
audience: llm
---

# justLLAMA — Native Skills & MCP

justLLAMA gives a chat model tools through **two parallel systems**. Both emit
OpenAI-compatible function schemas that are merged into the `tools` array of the
chat completion request (see `02-chat-modes-and-tools.md`). At execution time
the chat loop tries **native skills first, then MCP**.

## A. Native agent skills (in-process Python)

Native skills run inside the justLLAMA process. They are defined by subclassing
`AgentSkill` (`server/skills/base.py`) and implementing four methods:

- `get_name()` → short unique id (also the `skill_id` / tool name).
- `get_description()` → shown in Settings and used as the tool description.
- `get_tool_schema()` → an OpenAI function-calling schema dict.
- `execute(args, cancel_check=None)` → returns a **string** result fed back to
  the model. Long skills should poll `cancel_check()` and return early.

### Discovery & lifecycle (`SkillsManager`, `server/skills/manager.py`)
- On startup it imports every module in `justllama.server.skills` (bundled) and
  every `*.py` in the **user skills directory** (default
  `~/.local/share/justllama/skills/`), registering all `AgentSkill` subclasses.
- Each skill has an enable toggle stored at `skills/<skill_id>_enabled`; only
  **enabled** skills are advertised to the model (`get_active_tools_schema`).
- Execution runs on a single-worker `ThreadPoolExecutor` with a **per-skill
  timeout** (default 30s; a skill may raise it via a `timeout` attribute).
  Errors and timeouts are returned as strings, never raised into the chat loop.
- User skills are fully CRUD-managed from the UI: `get_skill_template`,
  `read_user_skill`, `save_user_skill` (validates filename, then reloads),
  `delete_user_skill`, and `reload_skills`.

### Bundled skills
| Skill | What it does | Notable |
|-------|--------------|---------|
| **time** (`time_skill.py`) | Returns current date/time. | Trivial, no side effects. |
| **terminal** (`terminal_skill.py`) | `terminal_run_command` runs a command in a persistent PTY session and waits for completion (returns stdout/stderr + exit code, default 30s, cap 120s); `terminal_send_keys` sends raw keystrokes to answer interactive prompts / send Ctrl-C. | **Privileged: arbitrary shell execution** in a persistent shared shell (`terminal_manager`). |
| **comfy_agent** (`comfy_agent.py`) | Lets the model author, run, and debug **ComfyUI API-format workflows** for image/video, and fetch bundled ComfyUI knowledge (`get_comfyui_knowledge`: core, model-compatibility, prompt-engineering, troubleshooting). | Timeout raised to **360s** (generation can take minutes). |
| **context7** (`context7_skill.py`) | Fetches up-to-date library/framework documentation. | Network access. |

The `comfy_knowledge/` directory ships four curated markdown guides that the
comfy_agent skill reads to author/fix workflows — an in-repo RAG-style knowledge
pack for ComfyUI.

## B. MCP tool servers (external processes)

`McpManager` (`server/mcp.py`) connects to **Model Context Protocol** servers
over **stdio**. It runs a dedicated asyncio event loop in a daemon thread; Qt
slots dispatch coroutines via `run_coroutine_threadsafe`.

- **Configuration**: enabled server commands live in `mcp/servers` (a list of
  shell command strings); a richer `mcp/servers_config` JSON holds objects with
  `command`, `enabled`, `env`, `name`, `description`. Servers are (re)connected
  on startup and whenever the setting changes.
- **Roots**: justLLAMA advertises two filesystem roots to servers that request
  them — the models dir (`~/Documents/models`) and the gemma-skills dir.
- **Tool exposure**: `get_openai_tools()` lists every connected server's tools
  and formats them as OpenAI function schemas; a `tool_name → session` map
  routes execution.
- **Execution**: `execute_tool(name, arguments)` calls the owning session
  (30s timeout) and flattens the MCP result content (text, `[Image Content]`,
  `[Embedded Resource: …]`) into a string.
- **Curated catalog**: `AppSettings.get_skills_catalog()` offers a few
  ready-to-add servers (Maestro workflow, Gemma-Dev knowledge, Playwright
  browser automation, filesystem). Example server:
  `npx -y @modelcontextprotocol/server-everything`.
- Emits `server_status_changed(command, "connected"|"error", message)`.

## Skills vs MCP — when each applies

| | Native skills | MCP servers |
|---|---------------|-------------|
| Process | In justLLAMA process | Separate subprocess (stdio) |
| Language | Python (`AgentSkill`) | Any (per MCP spec) |
| Added by | Bundled or user `.py` in skills dir | Shell command in Settings |
| Execution routing | **checked first** | fallback after skills |
| Timeout | per-skill (30s default) | 30s |

## Guidance for an operating model

- **Terminal and ComfyUI agent skills have real host effects** — arbitrary shell
  and process/GPU work. Confirm intent for destructive commands; read state
  before mutating; report exact returned output.
- Tool names are global; a native skill and an MCP tool with the same name would
  resolve to the **native** one first.
- Only **enabled** native skills and **connected** MCP servers are available; a
  tool being described in docs does not mean it is currently active.
- MCP servers inherit `os.environ` plus their configured `env`; do not leak
  secrets into server args or logs.
