"""Department-to-agent factory routing.

Direct routing: user's department determines which agent factory to call.
Each factory creates agent config with per-user Composio tools.
No LLM-based classification needed — the department is known from JWT claims.
"""

from agents.admin_agent import create_admin_agent
from agents.sales_agent import create_sales_agent
from agents.ops_agent import create_ops_agent
from agents.finance_agent import create_finance_agent
from agents.executive_agent import create_executive_agent

DEPARTMENT_FACTORIES: dict[str, callable] = {
    "admin": create_admin_agent,
    "sales": create_sales_agent,
    "operations": create_ops_agent,
    "finance": create_finance_agent,
    "executive": create_executive_agent,
}


def get_agent_for_department(
    department: str,
    user_id: str,
    *,
    email: str = "",
    name: str = "",
) -> dict:
    """Create agent config for a department with per-user Composio tools and pinned identity.

    Returns: {instruction: str, tools: list[dict]}
    Falls back to admin agent factory for unknown departments.
    """
    factory = DEPARTMENT_FACTORIES.get(department, create_admin_agent)
    return factory(user_id, email=email, name=name)
