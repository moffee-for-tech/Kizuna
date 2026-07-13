"""Tests for Composio v3 tool configuration."""

import sys
import pytest
from unittest.mock import MagicMock, patch


def test_department_toolkits_has_all_departments():
    """Every valid department must have a toolkit list."""
    from agents.tools import DEPARTMENT_TOOLKITS

    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        assert dept in DEPARTMENT_TOOLKITS, f"Missing toolkits for {dept}"
        assert isinstance(DEPARTMENT_TOOLKITS[dept], list)
        assert len(DEPARTMENT_TOOLKITS[dept]) > 0


def test_all_departments_have_google_suite():
    """Every department should have the core Google suite."""
    from agents.tools import DEPARTMENT_TOOLKITS

    google_core = {"gmail", "google_chat", "googlecalendar", "googlemeet", "googledrive", "googlesheets", "googledocs", "googleslides"}
    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        dept_toolkits = set(DEPARTMENT_TOOLKITS[dept])
        missing = google_core - dept_toolkits
        assert not missing, f"{dept} missing Google suite toolkits: {missing}"


def test_executive_has_superset_of_toolkits():
    """Executive should have access to toolkits from all other departments."""
    from agents.tools import DEPARTMENT_TOOLKITS

    executive_toolkits = set(DEPARTMENT_TOOLKITS["executive"])
    for dept in ["admin", "sales", "operations", "finance"]:
        dept_toolkits = set(DEPARTMENT_TOOLKITS[dept])
        assert executive_toolkits & dept_toolkits, f"Executive missing toolkits from {dept}"


def test_get_composio_tools_requires_user_id_and_department():
    """get_composio_tools must accept user_id and department."""
    import inspect
    from agents.tools import get_composio_tools

    sig = inspect.signature(get_composio_tools)
    params = list(sig.parameters.keys())
    assert "user_id" in params
    assert "department" in params


def test_get_composio_tools_unknown_department():
    """Unknown department should return empty list."""
    from agents.tools import get_composio_tools

    tools = get_composio_tools("user_1", "nonexistent")
    assert tools == []


def test_get_composio_tools_no_api_key(monkeypatch):
    """Should return empty list if COMPOSIO_API_KEY is not set."""
    monkeypatch.setattr("agents.tools.COMPOSIO_API_KEY", "")
    from agents.tools import get_composio_tools

    tools = get_composio_tools("user_1", "admin")
    assert tools == []
