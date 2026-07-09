"""Base class for native agent skills.

Every skill must subclass `AgentSkill` and implement the four required
methods. The SkillsManager discovers subclasses and routes LLM tool
calls to them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

class AgentSkill(ABC):
    """Abstract base class for a native agent skill.

    Subclasses MUST implement:
        - get_name()
        - get_description()
        - get_tool_schema()
        - execute()
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return a short, unique identifier for this skill (e.g. 'web_search')."""
        ...

    @abstractmethod
    def get_description(self) -> str:
        """Return a human-readable description shown in the Settings UI."""
        ...

    @abstractmethod
    def get_tool_schema(self) -> dict:
        """Return an OpenAI-compatible function-calling tool schema dict.

        Example::

            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Returns the current date and time.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            }
        """
        ...

    @abstractmethod
    def execute(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        """Execute the skill with the given arguments.

        Args:
            args: Parsed JSON arguments from the LLM tool call.
            cancel_check: Optional callable that returns True when the
                user requests cancellation.  Long-running skills SHOULD
                poll this periodically and raise or return early.

        Returns:
            A string result to feed back to the LLM as the tool response.
        """
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def skill_id(self) -> str:
        """Stable ID derived from the class name; used as the Settings key."""
        return self.get_name()
