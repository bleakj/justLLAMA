"""Tests for justllama.memory — short-term, long-term, and manager."""

from __future__ import annotations

import json
import sys

import pytest

from PySide6.QtWidgets import QApplication

from justllama.memory.short_term import ShortTermMemory
from justllama.memory.long_term import LongTermMemory
from justllama.memory.manager import MemoryManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------



@pytest.fixture()
def short_term(qapp):
    """Fresh ShortTermMemory per test."""
    return ShortTermMemory(max_size=50)


@pytest.fixture()
def long_term(tmp_path, qapp):
    """Fresh LongTermMemory backed by a temp SQLite database."""
    db = str(tmp_path / "test_memory.db")
    return LongTermMemory(db_path=db)


@pytest.fixture()
def manager(tmp_path, qapp):
    """Fresh MemoryManager with temp-backed long-term memory."""
    db = str(tmp_path / "manager_memory.db")
    lt = LongTermMemory(db_path=db)
    return MemoryManager(long_term=lt, enabled=False)


# ===================================================================
# Short-term memory tests
# ===================================================================

class TestShortTermMemory:
    def test_add_and_get_history(self, short_term):
        short_term.add_message("user", "Hello")
        short_term.add_message("assistant", "Hi there")
        short_term.add_message("user", "How are you?")

        raw = short_term.get_history(-1)
        history = json.loads(raw)

        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there"}
        assert history[2] == {"role": "user", "content": "How are you?"}

    def test_history_limit(self, short_term):
        for i in range(5):
            short_term.add_message("user", f"msg-{i}")

        raw = short_term.get_history(3)
        history = json.loads(raw)

        assert len(history) == 3
        assert [m["content"] for m in history] == ["msg-2", "msg-3", "msg-4"]

    def test_clear(self, short_term):
        short_term.add_message("user", "A")
        short_term.add_message("assistant", "B")
        assert short_term.count() == 2

        short_term.clear()
        assert short_term.count() == 0

    def test_max_size(self):
        st = ShortTermMemory(max_size=3)
        for i in range(5):
            st.add_message("user", f"msg-{i}")

        assert st.count() == 3
        raw = st.get_history(-1)
        history = json.loads(raw)
        assert [m["content"] for m in history] == ["msg-2", "msg-3", "msg-4"]

    def test_format_for_prompt(self, short_term):
        short_term.add_message("user", "What is 2+2?")
        short_term.add_message("assistant", "4")

        prompt = short_term.format_for_prompt()

        assert "User: What is 2+2?" in prompt
        assert "Assistant: 4" in prompt
        assert "\n" in prompt


# ===================================================================
# Long-term memory tests
# ===================================================================

class TestLongTermMemory:
    def test_store_and_search(self, long_term):
        long_term.store("The capital of France is Paris", "fact")
        long_term.store("Python is a programming language", "fact")
        long_term.store("I prefer dark mode", "preference")

        raw = long_term.search("France")
        results = json.loads(raw)

        assert len(results) >= 1
        assert any("Paris" in r["content"] for r in results)

    def test_forget(self, long_term):
        mid = long_term.store("Temporary memory", "general")
        assert long_term.count() == 1

        forgotten = long_term.forget(mid)
        assert forgotten is True
        assert long_term.count() == 0

    def test_count(self, long_term):
        for i in range(5):
            long_term.store(f"Memory {i}", "general")

        assert long_term.count() == 5

    def test_clear(self, long_term):
        for i in range(3):
            long_term.store(f"Memory {i}", "general")
        assert long_term.count() == 3

        long_term.clear()
        assert long_term.count() == 0

    def test_list_by_category(self, long_term):
        long_term.store("Water boils at 100C", "fact")
        long_term.store("Pi is about 3.14", "fact")
        long_term.store("I like coffee", "preference")

        raw = long_term.list_by_category("fact")
        results = json.loads(raw)

        assert len(results) == 2
        assert all(r["category"] == "fact" for r in results)

    def test_list_all(self, long_term):
        long_term.store("Alpha", "fact")
        long_term.store("Beta", "preference")
        long_term.store("Gamma", "general")

        all_memories = long_term.list_all()

        assert len(all_memories) == 3
        contents = {m["content"] for m in all_memories}
        assert contents == {"Alpha", "Beta", "Gamma"}


# ===================================================================
# Manager tests
# ===================================================================

class TestMemoryManager:
    def test_add_user_message(self, manager):
        assert manager.short_term.count() == 0

        manager.add_message("user", "Hello world")
        assert manager.short_term.count() == 1

    def test_retrieve_context_disabled(self, manager):
        """When disabled, retrieve_context returns empty JSON array."""
        result = manager.retrieve_context("anything")
        assert result == "[]"

    def test_retrieve_context_enabled(self, manager):
        manager.set_enabled(True)
        manager.long_term.store("The sky is blue", "fact")
        raw = manager.retrieve_context("blue sky")
        results = json.loads(raw)

        assert len(results) >= 1

    def test_store_memory_disabled(self, manager):
        """When disabled, store_memory returns empty string."""
        result = manager.store_memory("Important fact")
        assert result == ""

    def test_store_memory_enabled(self, manager):
        manager.set_enabled(True)

        result = manager.store_memory("Important fact", "fact")

        assert isinstance(result, str)
        assert len(result) > 0
        assert manager.long_term.count() == 1

    def test_clear_all(self, manager):
        manager.add_message("user", "msg-1")
        manager.add_message("assistant", "msg-2")
        assert manager.short_term.count() == 2
        manager.set_enabled(True)
        manager.store_memory("Stored fact")

        assert manager.short_term.count() == 2
        assert manager.long_term.count() == 1

        manager.clear_all()

        assert manager.short_term.count() == 0
        assert manager.long_term.count() == 0

    def test_stats(self, manager):
        manager.add_message("user", "test")
        manager.set_enabled(True)
        manager.store_memory("Fact A", "fact")
        manager.store_memory("Fact B", "fact")

        raw = manager.stats()
        data = json.loads(raw)

        assert "short_term_count" in data
        assert "long_term_count" in data
        assert "enabled" in data
        assert data["short_term_count"] == 1
        assert data["long_term_count"] == 2
        assert data["enabled"] is True
