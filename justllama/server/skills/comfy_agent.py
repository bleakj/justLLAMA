"""Native agent skill: ComfyUI workflow generation bridge.

This skill connects justLLAMA's chat LLM (which already routes tool calls
through :class:`~justllama.server.skills.manager.SkillsManager`) to the
ComfyUI generation backends. It is the in-repo realization of the value
surveyed in the ``artokun/comfyui-mcp`` repository: instead of only running
the hardcoded ``flux_workflow.json`` / ``wan_workflow.json`` templates from a
UI button, the agent can now author a ComfyUI API-format workflow itself,
execute it, and read back the exact error trace when it fails — then consult
the bundled ``comfy_knowledge`` guides (sourced from comfyui-mcp) to fix it.

Knowledge files (comfyui-core, model-compatibility, prompt-engineering,
troubleshooting) live in this package's ``comfy_knowledge/`` directory and
were retrieved read-only from the upstream repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from justllama.server.skills.base import AgentSkill
from justllama.server.generation_registry import get_image_manager, get_video_manager

_KNOWLEDGE_DIR = Path(__file__).parent / "comfy_knowledge"

# Generation can take minutes (video); the SkillsManager honors this per-skill
# budget instead of the default 30s cap.
timeout = 360.0

_KNOWLEDGE_TOPICS = {
    "comfyui-core": "comfyui-core.md",
    "model-compatibility": "model-compatibility.md",
    "prompt-engineering": "prompt-engineering.md",
    "troubleshooting": "troubleshooting.md",
}


class ComfyAgentSkill(AgentSkill):
    """Lets the LLM author, run, and debug ComfyUI workflows."""

    def get_name(self) -> str:
        return "comfy_agent"

    def get_description(self) -> str:
        return (
            "ComfyUI workflow generation and troubleshooting. Use to generate "
            "images/videos from a ComfyUI API-format workflow JSON that YOU author "
            "(any model architecture), and to read back exact ComfyUI error traces "
            "for autonomous debugging. Pair with get_comfyui_knowledge to fetch the "
            "ComfyUI API format, model-compatibility, prompt-engineering, and "
            "troubleshooting guides before authoring or fixing a workflow."
        )

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "comfy_agent",
                "description": self.get_description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": (
                                "generate = run a ComfyUI workflow and return the "
                                "output file path or the error trace. knowledge = "
                                "return a reference guide to help author/fix workflows."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["image", "video"],
                            "description": "Required for action=generate. Image or video pipeline.",
                        },
                        "workflow_json": {
                            "type": "string",
                            "description": (
                                "Required for action=generate. A ComfyUI API-format "
                                "workflow as a JSON string: an object mapping string "
                                "node IDs to {class_type, inputs}. Use PROMPT_PLACEHOLDER "
                                "and MODEL_PLACEHOLDER to let justLLAMA inject the "
                                "selected model/prompt, or hard-code both."
                            ),
                        },
                        "topic": {
                            "type": "string",
                            "enum": list(_KNOWLEDGE_TOPICS.keys()),
                            "description": "Required for action=knowledge. Which guide to fetch.",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    def execute(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        action = (args.get("action") or "").strip().lower()

        if action == "knowledge":
            return self._get_knowledge(args.get("topic"))

        if action == "generate":
            return self._generate(args, cancel_check)

        return (
            "Error: unknown action. Use action='generate' (with kind + "
            "workflow_json) or action='knowledge' (with topic)."
        )

    # ── action handlers ──────────────────────────────────────────────

    def _generate(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        kind = (args.get("kind") or "").strip().lower()
        workflow_json = args.get("workflow_json")

        if kind not in ("image", "video"):
            return "Error: action='generate' requires kind='image' or 'kind='video'."
        if not isinstance(workflow_json, str) or not workflow_json.strip():
            return "Error: action='generate' requires a non-empty 'workflow_json' string."

        manager = get_image_manager() if kind == "image" else get_video_manager()
        if manager is None:
            return (
                f"Error: {kind} generation backend is not available "
                "(imageGenManager/videoGenManager not registered)."
            )

        try:
            manager.generate_from_workflow(workflow_json)
        except Exception as e:  # defensive: surface sync failures cleanly
            return f"Error starting {kind} generation: {e}"

        output, error = manager.wait_for_generation(cancel_check=cancel_check)
        if error:
            return (
                f"ComfyUI {kind} generation failed:\n{error}\n\n"
                "Consult the 'troubleshooting' knowledge guide and the error "
                "trace above, then re-run with a corrected workflow_json."
            )
        if output:
            return f"ComfyUI {kind} generation succeeded. Output file: {output}"
        return f"ComfyUI {kind} generation finished but produced no output file."

    def _get_knowledge(self, topic: str | None) -> str:
        key = (topic or "").strip().lower()
        filename = _KNOWLEDGE_TOPICS.get(key)
        if filename is None:
            return (
                "Error: unknown topic. Choose one of: "
                + ", ".join(_KNOWLEDGE_TOPICS.keys())
            )
        path = _KNOWLEDGE_DIR / filename
        if not path.is_file():
            return f"Error: knowledge file missing: {path}"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading knowledge file '{filename}': {e}"
