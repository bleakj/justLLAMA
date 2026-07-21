"""Tests for the native agent skills system.

Covers:
    - AgentSkill base class contract
    - SkillsManager discovery, toggling, tool schema injection, and execution
    - Integration with ChatRunner tool routing
"""

import time
from unittest.mock import MagicMock

import pytest

from justllama.server.skills.base import AgentSkill
from justllama.server.skills.manager import SkillsManager
from justllama.server.skills.time_skill import GetCurrentTime


# ------------------------------------------------------------------
# AgentSkill base class
# ------------------------------------------------------------------


class TestAgentSkillBase:
    def test_cannot_instantiate_abstract(self):
        """AgentSkill is abstract; bare instantiation must fail."""
        with pytest.raises(TypeError):
            AgentSkill()  # type: ignore[abstract]

    def test_time_skill_implements_contract(self):
        skill = GetCurrentTime()
        assert skill.get_name() == "get_current_time"
        assert isinstance(skill.get_description(), str)
        assert len(skill.get_description()) > 0

        schema = skill.get_tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_current_time"
        assert "parameters" in schema["function"]

    def test_skill_id_property(self):
        skill = GetCurrentTime()
        assert skill.skill_id == "get_current_time"

    def test_execute_returns_string(self):
        skill = GetCurrentTime()
        result = skill.execute({})
        assert isinstance(result, str)
        # Should be a valid ISO datetime string
        assert "T" in result  # basic sanity check


# ------------------------------------------------------------------
# SkillsManager
# ------------------------------------------------------------------


class TestSkillsManager:
    @pytest.fixture
    def manager(self):
        """Create a fresh SkillsManager instance."""
        return SkillsManager()

    def test_discover_skills(self, manager):
        """SkillsManager should discover the time skill."""
        skills = manager.get_skills_list()
        ids = [s["id"] for s in skills]
        assert "get_current_time" in ids

    def test_skill_metadata(self, manager):
        skills = manager.get_skills_list()
        time_skill = next(s for s in skills if s["id"] == "get_current_time")
        assert time_skill["name"] == "get_current_time"
        assert time_skill["description"]
        assert isinstance(time_skill["enabled"], bool)

    def test_toggle_persistence(self, manager):
        """Toggling a skill should persist via AppSettings."""
        skill_id = "get_current_time"
        # Ensure known state
        manager.set_enabled(skill_id, False)
        assert manager.is_enabled(skill_id) is False

        manager.set_enabled(skill_id, True)
        assert manager.is_enabled(skill_id) is True

        manager.set_enabled(skill_id, False)
        assert manager.is_enabled(skill_id) is False

    def test_get_active_tools_schema_off(self, manager):
        """When skill is disabled, no tools should be returned."""
        manager.set_enabled("get_current_time", False)
        tools = manager.get_active_tools_schema()
        assert not any(t["function"]["name"] == "get_current_time" for t in tools)

    def test_get_active_tools_schema_on(self, manager):
        """When skill is enabled, its schema should appear."""
        manager.set_enabled("get_current_time", True)
        tools = manager.get_active_tools_schema()
        assert any(t["function"]["name"] == "get_current_time" for t in tools)
    def test_has_tool(self, manager):
        assert manager.has_tool("get_current_time") is True
        assert manager.has_tool("nonexistent_tool") is False

    def test_execute_tool(self, manager):
        manager.set_enabled("get_current_time", True)
        result = manager.execute_tool("get_current_time", {})
        assert isinstance(result, str)
        assert "T" in result

    def test_execute_tool_unknown(self, manager):
        result = manager.execute_tool("nonexistent", {})
        assert "Error" in result

    def test_execute_tool_timeout(self, manager):
        """A skill that takes too long should return a timeout error."""

        class SlowSkill(AgentSkill):
            def get_name(self):
                return "slow_skill"

            def get_description(self):
                return "A skill that sleeps forever"

            def get_tool_schema(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "slow_skill",
                        "description": "slow",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }

            def execute(self, args, cancel_check=None):
                time.sleep(60)
                return "done"

        manager._skills["slow_skill"] = SlowSkill()
        result = manager.execute_tool("slow_skill", {}, timeout=0.1)
        assert "timed out" in result

    def test_execute_tool_cancel_check(self, manager):
        """Skills should respect the cancel_check callable."""

        class CancellableSkill(AgentSkill):
            def get_name(self):
                return "cancellable"

            def get_description(self):
                return "Checks cancellation"

            def get_tool_schema(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "cancellable",
                        "description": "cancellable",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }

            def execute(self, args, cancel_check=None):
                if cancel_check and cancel_check():
                    return "cancelled"
                return "completed"

        manager._skills["cancellable"] = CancellableSkill()

        # Not cancelled
        result = manager.execute_tool("cancellable", {}, cancel_check=lambda: False)
        assert result == "completed"

        # Cancelled
        result = manager.execute_tool("cancellable", {}, cancel_check=lambda: True)
        assert result == "cancelled"


# ------------------------------------------------------------------
# ChatRunner integration
# ------------------------------------------------------------------


class TestChatRunnerSkillsIntegration:
    def test_chat_runner_accepts_skills_manager(self):
        """ChatRunner should accept and store skills_manager."""
        from justllama.server.chat_manager import ChatRunner

        mock_skills = MagicMock()
        runner = ChatRunner([], {}, mcp_manager=None, skills_manager=mock_skills)
        assert runner.skills_manager is mock_skills

    def test_chat_manager_accepts_skills_manager(self):
        """ChatManager should accept and store skills_manager."""
        from justllama.server.chat_manager import ChatManager

        mock_skills = MagicMock()
        manager = ChatManager(mcp_manager=None, skills_manager=mock_skills)
        assert manager.skills_manager is mock_skills


# ------------------------------------------------------------------
# SkillsManager shutdown
# ------------------------------------------------------------------


class TestSkillsManagerShutdown:
    def test_shutdown_does_not_raise(self):
        manager = SkillsManager()
        manager.shutdown()  # should not raise
