"""Native agent skills for Context7 documentation lookup.

Allows the agent to search for library IDs and query up-to-date documentation.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable

from justllama.server.skills.base import AgentSkill


class Context7LibrarySkill(AgentSkill):
    """Skill that resolves a library name to a Context7 library ID."""

    timeout = 60.0

    def get_name(self) -> str:
        return "context7_library"

    def get_description(self) -> str:
        return "Resolves a library name to a Context7 library ID for documentation lookup."

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "context7_library",
                "description": "Searches Context7 to find the exact library ID for a given framework/library name. You must use the returned ID (format: /org/repo) in subsequent calls to 'context7_docs'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The name of the library (e.g., 'React', 'Next.js', 'Prisma').",
                        },
                        "query": {
                            "type": "string",
                            "description": "The specific question or topic you want documentation for. Being specific improves search relevance.",
                        },
                    },
                    "required": ["name", "query"],
                },
            },
        }

    def execute(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        name = args.get("name")
        query = args.get("query")
        if not name or not query:
            return "Error: Both 'name' and 'query' are required."

        if not shutil.which("npx"):
            return "Error: 'npx' command not found. Node.js must be installed to use this skill."

        cmd = ["npx", "ctx7@latest", "library", name, query]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip() or "No results found."
        except subprocess.CalledProcessError as e:
            return f"Error executing context7 library lookup:\n{e.stderr}"
        except Exception as e:
            return f"Error: {e}"


class Context7DocsSkill(AgentSkill):
    """Skill that queries up-to-date documentation using a Context7 library ID."""

    timeout = 60.0

    def get_name(self) -> str:
        return "context7_docs"

    def get_description(self) -> str:
        return "Fetches documentation for a library using its Context7 library ID."

    def get_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "context7_docs",
                "description": "Queries up-to-date documentation for a specific library. You must first use 'context7_library' to get the library_id (e.g., '/facebook/react').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "library_id": {
                            "type": "string",
                            "description": "The library ID obtained from context7_library (format: /org/repo).",
                        },
                        "query": {
                            "type": "string",
                            "description": "Your detailed question or search query.",
                        },
                    },
                    "required": ["library_id", "query"],
                },
            },
        }

    def execute(self, args: dict, cancel_check: Callable[[], bool] | None = None) -> str:
        library_id = args.get("library_id")
        query = args.get("query")
        if not library_id or not query:
            return "Error: Both 'library_id' and 'query' are required."

        if not shutil.which("npx"):
            return "Error: 'npx' command not found. Node.js must be installed to use this skill."

        cmd = ["npx", "ctx7@latest", "docs", library_id, query]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip() or "No documentation found for this query."
        except subprocess.CalledProcessError as e:
            return f"Error fetching docs:\n{e.stderr}"
        except Exception as e:
            return f"Error: {e}"
