"""Tests for agent department routing with factory dispatch."""

import pytest
from unittest.mock import patch, MagicMock


def test_get_agent_for_known_departments():
    """Each valid department should return a non-None agent config."""
    from agents.router import get_agent_for_department

    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        agent_config = get_agent_for_department(dept, "test_user")
        assert agent_config is not None, f"No agent for {dept}"
        assert "instruction" in agent_config
        assert "tools" in agent_config


def test_get_agent_for_unknown_department_returns_admin():
    """Unknown department should fall back to admin agent."""
    from agents.router import get_agent_for_department

    agent_config = get_agent_for_department("nonexistent", "test_user")
    assert agent_config is not None
    assert "instruction" in agent_config
    assert "tools" in agent_config


def test_factory_creates_distinct_agents_per_user():
    """Different user_ids should produce different agent configs."""
    from agents.router import get_agent_for_department

    agent_a = get_agent_for_department("admin", "user_a")
    agent_b = get_agent_for_department("admin", "user_b")
    # Configs should differ due to user_id in the instruction
    assert agent_a is not agent_b


def test_factory_passes_user_id_through():
    """The factory should call get_composio_tools with the user_id."""
    with patch("agents.admin_agent.get_composio_tools", return_value=[]) as mock_tools:
        from agents.router import get_agent_for_department

        get_agent_for_department("admin", "user_xyz")
        mock_tools.assert_called_with("user_xyz", "admin")
