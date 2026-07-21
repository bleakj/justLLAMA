"""Unified memory API — orchestrates short-term and long-term memory."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Slot

from justllama.memory.short_term import ShortTermMemory
from justllama.memory.long_term import LongTermMemory


class MemoryManager(QObject):
    """Unified API for memory management.

    On each chat turn:
    1. Retrieve relevant long-term memories (FTS search).
    2. Include short-term history.
    3. Augment the system prompt with retrieved context.
    4. After response, optionally store new memories.
    """

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
        enabled: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._short_term = short_term or ShortTermMemory(parent=self)
        self._long_term = long_term or LongTermMemory(parent=self)
        self._enabled = enabled

    @property
    def short_term(self) -> ShortTermMemory:
        return self._short_term

    @property
    def long_term(self) -> LongTermMemory:
        return self._long_term

    @Slot(bool)
    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    @Slot(result=bool)
    def is_enabled(self) -> bool:
        return self._enabled

    @Slot(str, str)
    def add_message(self, role: str, content: str):
        """Add a message to short-term memory (QML-friendly alias)."""
        self._short_term.add_message(role, content)
    @Slot(dict)
    def add_raw_message(self, message: dict):
        """Add a raw message dictionary directly to short-term memory."""
        self._short_term.add_raw_message(message)
    @Slot(int, result=str)
    def get_short_term_history(self, limit: int = -1) -> str:
        """Get short-term history as JSON (QML-friendly)."""
        return self._short_term.get_history(limit)

    @Slot(str, int, result=str)
    def retrieve_context(self, query: str, limit: int = 5) -> str:
        """Retrieve relevant long-term memories for context augmentation.

        Args:
            query: The user's message or query to search against.
            limit: Max memories to retrieve.

        Returns:
            JSON string — list of relevant memory dicts.
        """
        if not self._enabled:
            return "[]"
        return self._long_term.search(query, limit)

    @Slot(result=str)
    def get_system_prompt_addition(self) -> str:
        """Build a context addition for the system prompt.

        Returns relevant long-term memories only. Short-term history is
        intentionally NOT included here: callers already send the full
        short-term conversation as real chat messages (via
        get_short_term_history), so embedding it again as text would duplicate
        the entire conversation in every request.
        """
        parts = []

        # Long-term context from recent interactions
        if self._enabled:
            # Pull the newest memories by recency (not an FTS match for the
            # literal word "recent", which would almost always be empty).
            recent = self._long_term.list_recent(3)
            memories = json.loads(recent)
            if memories:
                mem_lines = [m["content"] for m in memories]
                parts.append(
                    "Relevant memories:\n" + "\n".join(f"- {l}" for l in mem_lines)
                )

        return "\n\n".join(parts)

    @Slot(str, str, result=str)
    def store_memory(self, content: str, category: str = "general") -> str:
        """Store a new long-term memory.

        Returns:
            Memory ID.
        """
        if not self._enabled:
            return ""
        return self._long_term.store(content, category)

    @Slot()
    def clear_short_term(self):
        self._short_term.clear()

    @Slot()
    def clear_long_term(self):
        self._long_term.clear()

    @Slot()
    def clear_all(self):
        self._short_term.clear()
        self._long_term.clear()
    @Slot(result=str)
    def list_all_memories(self) -> str:
        """List all long-term memories (QML-friendly)."""
        return json.dumps(self._long_term.list_all())

    @Slot(str, result=str)
    def list_memories_by_category(self, category: str) -> str:
        """List memories by category (QML-friendly)."""
        return self._long_term.list_by_category(category)

    @Slot(str, result=bool)
    def forget_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID (QML-friendly).
        
        Returns True if a memory was actually deleted.
        """
        return self._long_term.forget(memory_id)

    @Slot(result=str)
    def stats(self) -> str:
        """Return memory statistics as JSON."""
        return json.dumps({
            "short_term_count": self._short_term.count(),
            "long_term_count": self._long_term.count(),
            "enabled": self._enabled,
        })
