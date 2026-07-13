"""Executive department agent factory — has cross-department tool access."""

from agents.prompts import get_agent_instruction
from agents.tools import get_composio_tools


def create_executive_agent(user_id: str, *, email: str = "", name: str = "") -> dict:
    """Create an executive agent with cross-department Composio tools and pinned identity."""
    return {
        "instruction": get_agent_instruction("executive", user_id=user_id, email=email, name=name),
        "tools": get_composio_tools(user_id, "executive"),
    }
