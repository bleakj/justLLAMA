"""In-memory short-term session context (deque-based, thread-safe)."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QObject, QMutex, QMutexLocker, Signal, Slot


class ShortTermMemory(QObject):
    """Deque-based in-memory conversation history.

    Thread-safe via QMutex. Signals emitted on state changes.

    Signals:
        message_added(str role, str content)
        history_cleared()
    """

    message_added = Signal(str, str)
    history_cleared = Signal()

    def __init__(self, max_size: int = 50, parent=None):
        super().__init__(parent)
        self._messages: deque[dict] = deque(maxlen=max_size)
        self._mutex = QMutex()

    @Slot(str, str)
    def add_message(self, role: str, content: str):
        """Add a message to short-term memory.

        Args:
            role: "system", "user", or "assistant".
            content: Message text.
        """
        with QMutexLocker(self._mutex):
            self._messages.append({"role": role, "content": content})
        self.message_added.emit(role, content)

    @Slot(int, result=str)
    def get_history(self, limit: int = -1) -> str:
        """Get recent message history as JSON string.

        Args:
            limit: Max messages to return (-1 = all).

        Returns:
            JSON string — list of {"role": str, "content": str}.
        """
        import json
        with QMutexLocker(self._mutex):
            if limit < 0:
                messages = list(self._messages)
            elif limit == 0:
                messages = []
            else:
                messages = list(self._messages)[-limit:]
        return json.dumps(messages)

    @Slot(result=list)
    def get_history_list(self) -> list[dict]:
        """Get history as a Python list (for direct QML access)."""
        with QMutexLocker(self._mutex):
            return list(self._messages)

    @Slot(result=int)
    def count(self) -> int:
        with QMutexLocker(self._mutex):
            return len(self._messages)

    @Slot()
    def clear(self):
        """Clear all messages from short-term memory."""
        with QMutexLocker(self._mutex):
            self._messages.clear()
        self.history_cleared.emit()

    @Slot(result=str)
    def format_for_prompt(self) -> str:
        """Format short-term history as a prompt-ready string.

        Returns the conversation history in a format suitable for
        injection into a chat completion prompt.
        """
        with QMutexLocker(self._mutex):
            if not self._messages:
                return ""
            lines = []
            for msg in self._messages:
                role = msg["role"].capitalize()
                lines.append(f"{role}: {msg['content']}")
            return "\n".join(lines)
