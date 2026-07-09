"""SkillsManager — registry and execution router for native agent skills.

Discovers all `AgentSkill` subclasses, tracks their enabled/disabled
state via `AppSettings`, and routes LLM tool calls to the appropriate
skill implementation.
"""

from __future__ import annotations
from pathlib import Path

import importlib
import importlib.util
import inspect
import os
import pkgutil
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable

from PySide6.QtCore import QObject, Slot, Signal

from justllama.config.settings import AppSettings
from justllama.server.skills.base import AgentSkill


class SkillsManager(QObject):
    """Manages native agent skills: discovery, state, and execution."""

    skills_changed = Signal()  # emitted when the skills list or toggles change

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._settings = AppSettings()
        self._skills: dict[str, AgentSkill] = {}
        self._skill_metadata: dict[str, dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="skill")
        os.makedirs(self._settings.user_skills_directory, exist_ok=True)
        self._discover_skills()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover_skills(self) -> None:
        """Import every module in the skills package and register AgentSkill subclasses."""
        self._skills.clear()
        self._skill_metadata.clear()

        # --- Internal (bundled) skills ---
        import justllama.server.skills as pkg
        for importer, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
            if modname.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"justllama.server.skills.{modname}")
                self._extract_skills(mod, is_custom=False, filename="")
            except Exception:
                print(f"[SkillsManager] Failed to import skill module '{modname}':")
                traceback.print_exc()

        # --- User (custom) skills ---
        user_dir = self._settings.user_skills_directory
        for py_file in sorted(Path(user_dir).glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(
                    f"justllama_user_skills.{py_file.stem}", py_file
                )
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
                self._extract_skills(mod, is_custom=True, filename=py_file.name)
            except Exception:
                print(f"[SkillsManager] Failed to load user skill '{py_file.name}':")
                traceback.print_exc()

        print(f"[SkillsManager] Discovered {len(self._skills)} skill(s): {list(self._skills.keys())}")

    def _extract_skills(self, mod, is_custom: bool, filename: str) -> None:
        """Scan *mod* for AgentSkill subclasses and register them."""
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if not issubclass(obj, AgentSkill) or obj is AgentSkill:
                continue
            try:
                instance = obj()
                sid = instance.skill_id
                if sid and sid not in self._skills:
                    self._skills[sid] = instance
                    self._skill_metadata[sid] = {
                        "is_custom": is_custom,
                        "filename": filename,
                    }
            except Exception:
                print(f"[SkillsManager] Failed to instantiate {name}:")
                traceback.print_exc()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _key(self, skill_id: str) -> str:
        return f"skills/{skill_id}_enabled"

    def is_enabled(self, skill_id: str) -> bool:
        return self._settings.get_bool(self._key(skill_id))

    @Slot(str, bool)
    def set_enabled(self, skill_id: str, enabled: bool) -> None:
        """Toggle a skill on or off. Called from QML."""
        self._settings.set_bool(self._key(skill_id), enabled)
        self.skills_changed.emit()

    # ------------------------------------------------------------------
    # QML-facing slots
    # ------------------------------------------------------------------

    @Slot(result=list)
    def get_skills_list(self) -> list[dict]:
        """Return a list of skill metadata dicts for the Settings UI.

        Each dict: {id, name, description, enabled, is_custom, filename}
        """
        result = []
        for sid, skill in sorted(self._skills.items()):
            meta = self._skill_metadata.get(sid, {})
            result.append({
                "id": sid,
                "name": skill.get_name(),
                "description": skill.get_description(),
                "enabled": self.is_enabled(sid),
                "is_custom": meta.get("is_custom", False),
                "filename": meta.get("filename", ""),
            })
        return result
    # ------------------------------------------------------------------
    # User skills CRUD (called from QML)
    # ------------------------------------------------------------------

    @Slot(result=str)
    def get_skill_template(self) -> str:
        """Return boilerplate Python code for a minimal AgentSkill."""
        return '''\
from justllama.server.skills.base import AgentSkill


class MySkill(AgentSkill):
    """A custom skill."""

    skill_id = "my_skill"

    def get_name(self) -> str:
        return "My Skill"

    def get_description(self) -> str:
        return "A short description of what this skill does."

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.skill_id,
                "description": self.get_description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "Input text",
                        }
                    },
                    "required": ["input"],
                },
            },
        }

    def execute(self, args: dict, cancel_check=None) -> str:
        user_input = args.get("input", "")
        return f"Hello from MySkill! You said: {user_input}"
'''

    @Slot(str, result=str)
    def read_user_skill(self, filename: str) -> str:
        """Return the text content of a custom skill file."""
        path = Path(self._settings.user_skills_directory) / filename
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    @Slot(str, str, result=bool)
    def save_user_skill(self, filename: str, code: str) -> bool:
        """Validate filename, write code, and reload skills. Returns success."""
        if not filename.endswith(".py") or "/" in filename or "\\" in filename:
            print(f"[SkillsManager] Invalid skill filename: {filename!r}")
            return False
        try:
            path = Path(self._settings.user_skills_directory) / filename
            path.write_text(code, encoding="utf-8")
            self.reload_skills()
            return True
        except Exception:
            print(f"[SkillsManager] Failed to save skill '{filename}':")
            traceback.print_exc()
            return False

    @Slot(str, result=bool)
    def delete_user_skill(self, filename: str) -> bool:
        """Validate filename, delete the file, and reload skills. Returns success."""
        if not filename.endswith(".py") or "/" in filename or "\\" in filename:
            print(f"[SkillsManager] Invalid skill filename for delete: {filename!r}")
            return False
        try:
            path = Path(self._settings.user_skills_directory) / filename
            if path.is_file():
                path.unlink()
            self.reload_skills()
            return True
        except Exception:
            print(f"[SkillsManager] Failed to delete skill '{filename}':")
            traceback.print_exc()
            return False

    def reload_skills(self) -> None:
        """Re-discover all skills and notify the UI."""
        self._discover_skills()
        self.skills_changed.emit()

    # ------------------------------------------------------------------
    # Tool-calling integration (called by ChatRunner)
    # ------------------------------------------------------------------

    def get_active_tools_schema(self) -> list[dict]:
        """Return OpenAI tool schemas for all currently enabled skills."""
        tools = []
        for sid, skill in self._skills.items():
            if self.is_enabled(sid):
                tools.append(skill.get_tool_schema())
        return tools

    def has_tool(self, name: str) -> bool:
        """Check whether a tool name belongs to any registered skill."""
        return name in self._skills

    def execute_tool(
        self,
        name: str,
        args: dict,
        cancel_check: Callable[[], bool] | None = None,
        timeout: float = 30.0,
    ) -> str:
        """Route execution to the matching skill, with a timeout.

        Args:
            name: Tool name (must match a registered skill_id).
            args: Parsed arguments dict from the LLM.
            cancel_check: Optional cancellation callable.
            timeout: Maximum seconds to wait before aborting.

        Returns:
            The skill's string result, or an error message.
        """
        skill = self._skills.get(name)
        if skill is None:
            return f"Error: no native skill named '{name}'"

        try:
            future = self._executor.submit(skill.execute, args, cancel_check)
            return future.result(timeout=timeout)
        except FutureTimeout:
            return f"Error: skill '{name}' timed out after {timeout}s"
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[SkillsManager] Skill '{name}' raised: {e}\n{tb}")
            return f"Error executing skill '{name}': {e}"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Shut down the executor pool."""
        self._executor.shutdown(wait=False)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _all_subclasses(cls: type) -> set[type]:
    """Recursively collect all subclasses of cls."""
    result: set[type] = set()
    work = [cls]
    while work:
        parent = work.pop()
        for child in parent.__subclasses__():
            if child not in result:
                result.add(child)
                work.append(child)
    return result
