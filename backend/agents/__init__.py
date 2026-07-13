"""Multi-agent system for Triton AI Chat Platform.

Uses OpenRouter (Gemini LLM) with Composio tools for department-specific agents.

Usage:
    from agents.router import get_agent_for_department
    from agents.runner import run_agent
"""

from agents.router import get_agent_for_department
from agents.runner import run_agent

__all__ = ["get_agent_for_department", "run_agent"]
