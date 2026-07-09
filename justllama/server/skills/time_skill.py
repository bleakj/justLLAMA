"""Native skill: get_current_time.

Returns the current date and time in ISO format. Useful as a
demonstration and for LLM queries about the current time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from justllama.server.skills.base import AgentSkill


class GetCurrentTime(AgentSkill):
    """Skill that returns the current date and time."""

    def get_name(self) -> str:
        return "get_current_time"

    def get_description(self) -> str:
        return "Returns the current date and time in ISO format."

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Returns the current date and time in ISO 8601 format (UTC).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    def execute(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        now = datetime.now(timezone.utc)
        return now.isoformat()
