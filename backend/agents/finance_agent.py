"""Finance department agent factory."""

from agents.prompts import get_agent_instruction
from agents.tools import get_composio_tools


def create_finance_agent(user_id: str, *, email: str = "", name: str = "") -> dict:
    """Create a finance agent with per-user Composio tools and pinned identity."""
    return {
        "instruction": get_agent_instruction("finance", user_id=user_id, email=email, name=name),
        "tools": get_composio_tools(user_id, "finance"),
    }
