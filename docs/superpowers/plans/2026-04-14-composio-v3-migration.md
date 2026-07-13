# Composio v3 SDK Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from deprecated Composio v1/v2 (`ComposioToolSet`) to v3 SDK (`Composio` + `GoogleAdkProvider`) with per-user tool sessions, enabling cross-tool orchestration scoped by department.

**Architecture:** Agent Factory pattern — each department has a factory function that creates a fresh ADK `Agent` per request with the user's Composio tools. The router dispatches to factories instead of singletons. MintMCP connector flow is kept as fallback.

**Tech Stack:** `composio>=1.0.0`, `composio-google-adk>=1.0.0`, `google-adk>=1.0.0`, `google-genai>=1.0.0`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/requirements.txt` | Modify | Swap `composio-core` for `composio` + `composio-google-adk` |
| `backend/agents/tools.py` | Rewrite | Composio v3 session manager — per-user tool creation |
| `backend/agents/admin_agent.py` | Rewrite | Factory function `create_admin_agent(user_id)` |
| `backend/agents/sales_agent.py` | Rewrite | Factory function `create_sales_agent(user_id)` |
| `backend/agents/ops_agent.py` | Rewrite | Factory function `create_ops_agent(user_id)` |
| `backend/agents/finance_agent.py` | Rewrite | Factory function `create_finance_agent(user_id)` |
| `backend/agents/executive_agent.py` | Rewrite | Factory function `create_executive_agent(user_id)` |
| `backend/agents/router.py` | Rewrite | Factory dispatch with `user_id` parameter |
| `backend/agents/__init__.py` | Modify | Update exports |
| `backend/routers/chat.py` | Modify | Pass `user_id` to `get_agent_for_department` |
| `backend/tests/test_agents_tools.py` | Rewrite | Test new v3 signature and toolkits |
| `backend/tests/test_agents_router.py` | Rewrite | Test factory dispatch with `user_id` |

---

### Task 1: Update Dependencies

**Files:**
- Modify: `backend/requirements.txt:23`

- [ ] **Step 1: Update requirements.txt**

Replace line 23 in `backend/requirements.txt`:

```
composio-core>=0.7.0
```

With these two lines:

```
composio>=1.0.0
composio-google-adk>=1.0.0
```

- [ ] **Step 2: Install new dependencies**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && pip install composio composio-google-adk`

Expected: Successful installation. `composio-core` is a dependency of `composio` so it stays transitively.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: swap composio-core for composio + composio-google-adk (v3 SDK)"
```

---

### Task 2: Rewrite `agents/tools.py` — Composio v3 Session Manager

**Files:**
- Rewrite: `backend/agents/tools.py`
- Rewrite: `backend/tests/test_agents_tools.py`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `backend/tests/test_agents_tools.py` with:

```python
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

    google_core = {"gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs"}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_tools.py -v`

Expected: Multiple FAILs — `DEPARTMENT_TOOLKITS` not found, `get_composio_tools` has wrong signature.

- [ ] **Step 3: Rewrite `agents/tools.py`**

Replace the entire contents of `backend/agents/tools.py` with:

```python
"""Composio v3 tool configuration per department.

Each department gets a scoped set of Composio-managed tool integrations.
Uses the GoogleAdkProvider to return ADK-native FunctionTool objects.
Tools are created per-user via composio.create(user_id=...).
"""

import logging

from agents.config import COMPOSIO_API_KEY

logger = logging.getLogger(__name__)

DEPARTMENT_TOOLKITS: dict[str, list[str]] = {
    "admin": [
        "gmail", "google_chat", "google_calendar",
        "google_drive", "google_sheets", "google_docs",
    ],
    "sales": [
        "hubspot", "gmail", "google_chat", "google_calendar",
        "google_drive", "google_sheets", "google_docs",
    ],
    "operations": [
        "jira", "gmail", "google_chat", "google_calendar",
        "google_drive", "google_sheets", "google_docs", "google_forms",
    ],
    "finance": [
        "gmail", "google_chat", "google_calendar",
        "google_drive", "google_sheets", "google_docs",
    ],
    "executive": [
        "hubspot", "jira", "gmail", "google_chat", "google_calendar",
        "google_drive", "google_sheets", "google_docs",
    ],
}


def get_composio_tools(user_id: str, department: str) -> list:
    """Get Composio tools for a user scoped to their department.

    Creates a per-user Composio session via the GoogleAdkProvider,
    returning ADK-native FunctionTool objects.

    Returns an empty list if:
    - Department not found in DEPARTMENT_TOOLKITS
    - COMPOSIO_API_KEY not set
    - Composio SDK initialization fails
    """
    toolkits = DEPARTMENT_TOOLKITS.get(department)
    if not toolkits:
        return []

    if not COMPOSIO_API_KEY:
        logger.warning("COMPOSIO_API_KEY not set — tools disabled")
        return []

    try:
        from composio import Composio
        from composio_google_adk import GoogleAdkProvider

        composio = Composio(provider=GoogleAdkProvider())
        session = composio.create(user_id=user_id)
        tools = session.tools(toolkits=toolkits)
        logger.info(
            f"Loaded {len(tools)} Composio tools for user={user_id} department={department}"
        )
        return tools
    except Exception as e:
        logger.warning(f"Failed to load Composio tools for {department}: {e}")
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_tools.py -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/tools.py backend/tests/test_agents_tools.py
git commit -m "feat: rewrite agents/tools.py for Composio v3 SDK with per-user sessions"
```

---

### Task 3: Convert Agent Files to Factories

**Files:**
- Rewrite: `backend/agents/admin_agent.py`
- Rewrite: `backend/agents/sales_agent.py`
- Rewrite: `backend/agents/ops_agent.py`
- Rewrite: `backend/agents/finance_agent.py`
- Rewrite: `backend/agents/executive_agent.py`

- [ ] **Step 1: Rewrite `admin_agent.py`**

Replace the entire contents of `backend/agents/admin_agent.py` with:

```python
"""Admin department ADK agent factory."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools


def create_admin_agent(user_id: str) -> Agent:
    """Create an admin ADK agent with per-user Composio tools."""
    return Agent(
        name="admin_agent",
        model=AGENT_MODEL,
        description=get_agent_description("admin"),
        instruction=get_agent_instruction("admin"),
        tools=get_composio_tools(user_id, "admin"),
    )
```

- [ ] **Step 2: Rewrite `sales_agent.py`**

Replace the entire contents of `backend/agents/sales_agent.py` with:

```python
"""Sales department ADK agent factory."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools


def create_sales_agent(user_id: str) -> Agent:
    """Create a sales ADK agent with per-user Composio tools."""
    return Agent(
        name="sales_agent",
        model=AGENT_MODEL,
        description=get_agent_description("sales"),
        instruction=get_agent_instruction("sales"),
        tools=get_composio_tools(user_id, "sales"),
    )
```

- [ ] **Step 3: Rewrite `ops_agent.py`**

Replace the entire contents of `backend/agents/ops_agent.py` with:

```python
"""Operations department ADK agent factory."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools


def create_ops_agent(user_id: str) -> Agent:
    """Create an operations ADK agent with per-user Composio tools."""
    return Agent(
        name="ops_agent",
        model=AGENT_MODEL,
        description=get_agent_description("operations"),
        instruction=get_agent_instruction("operations"),
        tools=get_composio_tools(user_id, "operations"),
    )
```

- [ ] **Step 4: Rewrite `finance_agent.py`**

Replace the entire contents of `backend/agents/finance_agent.py` with:

```python
"""Finance department ADK agent factory."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools


def create_finance_agent(user_id: str) -> Agent:
    """Create a finance ADK agent with per-user Composio tools."""
    return Agent(
        name="finance_agent",
        model=AGENT_MODEL,
        description=get_agent_description("finance"),
        instruction=get_agent_instruction("finance"),
        tools=get_composio_tools(user_id, "finance"),
    )
```

- [ ] **Step 5: Rewrite `executive_agent.py`**

Replace the entire contents of `backend/agents/executive_agent.py` with:

```python
"""Executive department ADK agent factory — has cross-department tool access."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools


def create_executive_agent(user_id: str) -> Agent:
    """Create an executive ADK agent with cross-department Composio tools."""
    return Agent(
        name="executive_agent",
        model=AGENT_MODEL,
        description=get_agent_description("executive"),
        instruction=get_agent_instruction("executive"),
        tools=get_composio_tools(user_id, "executive"),
    )
```

- [ ] **Step 6: Commit**

```bash
git add backend/agents/admin_agent.py backend/agents/sales_agent.py backend/agents/ops_agent.py backend/agents/finance_agent.py backend/agents/executive_agent.py
git commit -m "feat: convert 5 department agents from singletons to per-user factories"
```

---

### Task 4: Rewrite `agents/router.py` — Factory Dispatch

**Files:**
- Rewrite: `backend/agents/router.py`
- Rewrite: `backend/tests/test_agents_router.py`

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `backend/tests/test_agents_router.py` with:

```python
"""Tests for agent department routing with factory dispatch."""

import sys
import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Mock google.adk.agents.Agent and composio so tests don't need real packages."""

    class MockAgent:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_adk = MagicMock()
    mock_adk.agents.Agent = MockAgent

    mock_composio = MagicMock()
    mock_composio_adk = MagicMock()

    monkeypatch.setitem(sys.modules, "google", MagicMock())
    monkeypatch.setitem(sys.modules, "google.adk", mock_adk)
    monkeypatch.setitem(sys.modules, "google.adk.agents", mock_adk.agents)
    monkeypatch.setitem(sys.modules, "composio", mock_composio)
    monkeypatch.setitem(sys.modules, "composio_google_adk", mock_composio_adk)

    # Clear cached module imports so factories re-import cleanly
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("agents.") and mod_name != "agents.config":
            monkeypatch.delitem(sys.modules, mod_name, raising=False)


def test_get_agent_for_known_departments():
    """Each valid department should return a non-None agent."""
    from agents.router import get_agent_for_department

    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        agent = get_agent_for_department(dept, "test_user")
        assert agent is not None, f"No agent for {dept}"


def test_get_agent_for_unknown_department_returns_admin():
    """Unknown department should fall back to admin agent."""
    from agents.router import get_agent_for_department

    agent = get_agent_for_department("nonexistent", "test_user")
    assert agent is not None
    assert agent.name == "admin_agent"


def test_factory_creates_distinct_agents_per_user():
    """Different user_ids should produce different agent instances."""
    from agents.router import get_agent_for_department

    agent_a = get_agent_for_department("admin", "user_a")
    agent_b = get_agent_for_department("admin", "user_b")
    assert agent_a is not agent_b


def test_factory_passes_user_id_through():
    """The factory should call get_composio_tools with the user_id."""
    from unittest.mock import patch

    with patch("agents.tools.get_composio_tools", return_value=[]) as mock_tools:
        from agents.router import get_agent_for_department

        get_agent_for_department("admin", "user_xyz")
        mock_tools.assert_called_with("user_xyz", "admin")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_router.py -v`

Expected: FAILs — `get_agent_for_department` doesn't accept `user_id`, `DEPARTMENT_FACTORIES` not found.

- [ ] **Step 3: Rewrite `agents/router.py`**

Replace the entire contents of `backend/agents/router.py` with:

```python
"""Department-to-agent factory routing.

Direct routing: user's department determines which ADK agent factory to call.
Each factory creates a fresh Agent with per-user Composio tools.
No LLM-based classification needed — the department is known from JWT claims.
"""

from google.adk.agents import Agent

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


def get_agent_for_department(department: str, user_id: str) -> Agent:
    """Create an ADK agent for a department with per-user Composio tools.

    Falls back to admin agent factory for unknown departments.
    """
    factory = DEPARTMENT_FACTORIES.get(department, create_admin_agent)
    return factory(user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_router.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/router.py backend/tests/test_agents_router.py
git commit -m "feat: rewrite agents/router.py for factory dispatch with per-user tools"
```

---

### Task 5: Update `agents/__init__.py` and `routers/chat.py`

**Files:**
- Modify: `backend/agents/__init__.py`
- Modify: `backend/routers/chat.py:147,214`

- [ ] **Step 1: Update `agents/__init__.py`**

Replace the entire contents of `backend/agents/__init__.py` with:

```python
"""Google ADK multi-agent system for Polaris.

Usage:
    from agents.router import get_agent_for_department
    from agents.runner import run_agent
"""

from agents.router import get_agent_for_department
from agents.runner import run_agent

__all__ = ["get_agent_for_department", "run_agent"]
```

- [ ] **Step 2: Update `chat.py` — non-streaming endpoint**

In `backend/routers/chat.py`, find line 147:

```python
    agent = get_agent_for_department(department)
```

Replace with:

```python
    agent = get_agent_for_department(department, user_id)
```

- [ ] **Step 3: Update `chat.py` — streaming endpoint**

In `backend/routers/chat.py`, find line 214:

```python
            agent = get_agent_for_department(department)
```

Replace with:

```python
            agent = get_agent_for_department(department, user_id)
```

- [ ] **Step 4: Run all agent tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/ -v`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/agents/__init__.py backend/routers/chat.py
git commit -m "feat: wire chat router to per-user agent factories"
```

---

### Task 6: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/ -v`

Expected: All tests pass with no failures.

- [ ] **Step 2: Verify imports work**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -c "from agents.tools import DEPARTMENT_TOOLKITS, get_composio_tools; print('tools.py OK'); print(f'Departments: {list(DEPARTMENT_TOOLKITS.keys())}')"`

Expected: Prints `tools.py OK` and all 5 departments.

- [ ] **Step 3: Verify no old API references remain**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && grep -rn "ComposioToolSet\|composio-core\|get_tools(apps=" --include="*.py" --include="*.txt" .`

Expected: No matches (only docs/plans may have old references).

- [ ] **Step 4: Check no singleton agent references remain in production code**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && grep -rn "^admin_agent\s*=\|^sales_agent\s*=\|^ops_agent\s*=\|^finance_agent\s*=\|^executive_agent\s*=" --include="*.py" agents/`

Expected: No matches — all agents are now created via factories.
