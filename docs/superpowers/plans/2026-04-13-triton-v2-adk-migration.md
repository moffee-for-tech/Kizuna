# Triton V2 — ADK + Gemini + Composio Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Groq LLM + MintMCP tools with Google ADK multi-agent system (Gemini LLM) + Composio tool integrations, adding session summaries for long-term context.

**Architecture:** Five department-specific ADK agents (admin, sales, ops, finance, executive) are routed via user department. Each agent gets Composio tools scoped to its department. A runner bridges FastAPI routes to ADK agent execution. Session summaries auto-generate every 10 messages for long-term context.

**Tech Stack:** Google ADK (`google-adk`), Gemini 2.5 Flash (`google-genai`), Composio (`composio-core`), existing FastAPI + SQLAlchemy + Mem0/Qdrant stack.

---

## File Structure

### New Files

| File | Responsibility |
|---|---|
| `backend/agents/__init__.py` | Package init, exports `get_agent_for_department` |
| `backend/agents/config.py` | ADK + Gemini configuration constants |
| `backend/agents/tools.py` | Composio tool sets per department |
| `backend/agents/prompts.py` | Agent instruction strings per department (replaces `prompt_engine.py` for agent use) |
| `backend/agents/admin_agent.py` | Admin department ADK Agent |
| `backend/agents/sales_agent.py` | Sales department ADK Agent |
| `backend/agents/ops_agent.py` | Operations department ADK Agent |
| `backend/agents/finance_agent.py` | Finance department ADK Agent |
| `backend/agents/executive_agent.py` | Executive department ADK Agent |
| `backend/agents/router.py` | Department-to-agent routing map |
| `backend/agents/runner.py` | FastAPI-to-ADK bridge: builds context, runs agent, formats response |
| `backend/services/summary_service.py` | Session summary generation (every 10 messages) |
| `backend/tests/__init__.py` | Test package init |
| `backend/tests/test_agents_config.py` | Tests for agent config |
| `backend/tests/test_agents_tools.py` | Tests for Composio tool mapping |
| `backend/tests/test_agents_router.py` | Tests for department routing |
| `backend/tests/test_agents_runner.py` | Tests for runner context building + response formatting |
| `backend/tests/test_summary_service.py` | Tests for session summary logic |

### Modified Files

| File | Change |
|---|---|
| `backend/config.py` | Add `GEMINI_API_KEY`, `COMPOSIO_API_KEY`; remove Groq validation as required; keep Groq fields for backward compat |
| `backend/db/models.py` | Add `session_summary` (Text) + `summary_msg_count` (Integer) to `ChatSession` |
| `backend/db/database.py` | Add migration for new columns |
| `backend/services/memory_service.py` | Switch Mem0 LLM provider from Groq to Gemini |
| `backend/routers/chat.py` | Replace `chat_completion()` calls with `run_agent()`; add summary update after response |
| `backend/main.py` | Update deep health check from Groq to Gemini |
| `backend/requirements.txt` | Add `google-adk`, `google-genai`, `composio-core`; keep `groq`+`openai` for now |
| `backend/docker-compose.yml` | Add `GEMINI_API_KEY`, `COMPOSIO_API_KEY` env vars |

### Deleted Files

| File | Reason |
|---|---|
| `backend/services/groq_service.py` | Fully replaced by `agents/runner.py` + ADK agents |

### Untouched Files

| File | Reason |
|---|---|
| `backend/routers/auth.py` | Auth system unchanged |
| `backend/routers/sessions.py` | Session CRUD unchanged |
| `backend/routers/connectors.py` | Keep MintMCP connectors working as fallback (Composio is additive) |
| `backend/routers/upload.py` | Upload unchanged for now (Phase 5 PDF vision is a follow-up) |
| `backend/services/auth_service.py` | Auth logic unchanged |
| `backend/services/session_store.py` | Session operations unchanged |
| `backend/services/prompt_engine.py` | Kept for prompt templates API; agents use `agents/prompts.py` |
| `backend/middleware/rbac.py` | RBAC unchanged |
| `frontend/*` | API contract stays the same |

---

## Task 1: Install Dependencies + Update Config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py:7-97`
- Test: `backend/tests/test_agents_config.py`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Add these lines to `backend/requirements.txt`:

```
google-adk>=1.0.0
google-genai>=1.0.0
composio-core>=0.7.0
```

- [ ] **Step 2: Update config.py with new settings**

Add to the `Settings` class in `backend/config.py` after the Groq fields (line 10):

```python
    # Gemini (ADK)
    GEMINI_API_KEY: str = ""

    # Composio
    COMPOSIO_API_KEY: str = ""
```

Update `_validate_settings()` to validate `GEMINI_API_KEY` instead of `GROQ_API_KEY`:

```python
def _validate_settings():
    errors = []
    if not settings.GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is required — get one at https://aistudio.google.com")
    if not settings.JWT_SECRET:
        errors.append("JWT_SECRET is required — generate with: openssl rand -hex 32")
    elif len(settings.JWT_SECRET) < 32:
        errors.append("JWT_SECRET should be at least 32 characters")
    if errors:
        logger = logging.getLogger("triton.config")
        for e in errors:
            logger.error(f"Config error: {e}")
        raise SystemExit(
            "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )
```

- [ ] **Step 3: Create agents config module**

Create `backend/agents/__init__.py`:

```python
"""Google ADK multi-agent system for Triton V2."""
```

Create `backend/agents/config.py`:

```python
"""ADK and Gemini configuration."""

from config import settings

AGENT_MODEL = "gemini-2.5-flash"
GEMINI_API_KEY = settings.GEMINI_API_KEY
COMPOSIO_API_KEY = settings.COMPOSIO_API_KEY
```

- [ ] **Step 4: Write test for config**

Create `backend/tests/__init__.py`:

```python
```

Create `backend/tests/test_agents_config.py`:

```python
"""Tests for agents config module."""

import os
import pytest


def test_agent_model_is_gemini():
    """Agent model should be gemini-2.5-flash."""
    from agents.config import AGENT_MODEL
    assert AGENT_MODEL == "gemini-2.5-flash"


def test_config_reads_gemini_api_key(monkeypatch):
    """GEMINI_API_KEY should be read from settings."""
    from agents.config import GEMINI_API_KEY
    # Just verify it's a string (empty in test env is fine)
    assert isinstance(GEMINI_API_KEY, str)


def test_config_reads_composio_api_key(monkeypatch):
    """COMPOSIO_API_KEY should be read from settings."""
    from agents.config import COMPOSIO_API_KEY
    assert isinstance(COMPOSIO_API_KEY, str)
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_config.py -v`
Expected: 3 PASS

- [ ] **Step 6: Install dependencies**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && pip install google-adk google-genai composio-core`

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/agents/__init__.py backend/agents/config.py backend/tests/__init__.py backend/tests/test_agents_config.py
git commit -m "feat: add Gemini/ADK/Composio deps and config"
```

---

## Task 2: Composio Tool Configuration

**Files:**
- Create: `backend/agents/tools.py`
- Test: `backend/tests/test_agents_tools.py`

- [ ] **Step 1: Write test for tool mapping**

Create `backend/tests/test_agents_tools.py`:

```python
"""Tests for Composio tool configuration."""

import pytest
from unittest.mock import patch, MagicMock


def test_department_tools_has_all_departments():
    """Every valid department must have a tool list."""
    from agents.tools import DEPARTMENT_TOOLS
    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        assert dept in DEPARTMENT_TOOLS, f"Missing tools for {dept}"
        assert isinstance(DEPARTMENT_TOOLS[dept], list)
        assert len(DEPARTMENT_TOOLS[dept]) > 0


def test_executive_has_superset_of_tools():
    """Executive should have access to tools from all other departments."""
    from agents.tools import DEPARTMENT_TOOLS
    executive_tools = set(DEPARTMENT_TOOLS["executive"])
    for dept in ["admin", "sales", "operations", "finance"]:
        dept_tools = set(DEPARTMENT_TOOLS[dept])
        # Executive should have at least one tool from each department
        assert executive_tools & dept_tools, f"Executive missing tools from {dept}"


def test_get_composio_tools_returns_list():
    """get_composio_tools should return a list (even if Composio unavailable)."""
    from agents.tools import get_composio_tools
    # Without a real API key, should return empty list gracefully
    tools = get_composio_tools("admin")
    assert isinstance(tools, list)


def test_get_composio_tools_unknown_department():
    """Unknown department should return empty list."""
    from agents.tools import get_composio_tools
    tools = get_composio_tools("nonexistent")
    assert tools == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_tools.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement tools.py**

Create `backend/agents/tools.py`:

```python
"""Composio tool configuration per department.

Each department gets a scoped set of Composio-managed tool integrations.
Executive gets cross-department access to all tools.
"""

import logging

from agents.config import COMPOSIO_API_KEY

logger = logging.getLogger(__name__)

DEPARTMENT_TOOLS: dict[str, list[str]] = {
    "admin": [
        "GOOGLE_DOCS",
        "GMAIL",
        "GOOGLE_DRIVE",
        "GOOGLE_CALENDAR",
        "GOOGLE_SHEETS",
    ],
    "sales": [
        "HUBSPOT",
        "GMAIL",
        "GOOGLE_SHEETS",
        "GOOGLE_CALENDAR",
        "GOOGLE_DRIVE",
    ],
    "operations": [
        "JIRA",
        "GOOGLE_SHEETS",
        "GOOGLE_DOCS",
        "GOOGLE_DRIVE",
        "GOOGLE_FORMS",
    ],
    "finance": [
        "GOOGLE_SHEETS",
        "GOOGLE_DRIVE",
        "GOOGLE_DOCS",
        "GMAIL",
    ],
    "executive": [
        "HUBSPOT",
        "GOOGLE_SHEETS",
        "GOOGLE_DRIVE",
        "GOOGLE_DOCS",
        "GMAIL",
        "JIRA",
        "GOOGLE_CALENDAR",
    ],
}


def get_composio_tools(department: str) -> list:
    """Get Composio MCP tools for a department.

    Returns an empty list if:
    - Department not found
    - COMPOSIO_API_KEY not set
    - Composio SDK initialization fails
    """
    apps = DEPARTMENT_TOOLS.get(department)
    if not apps:
        return []

    if not COMPOSIO_API_KEY:
        logger.warning("COMPOSIO_API_KEY not set — tools disabled")
        return []

    try:
        from composio import ComposioToolSet

        toolset = ComposioToolSet(api_key=COMPOSIO_API_KEY)
        tools = toolset.get_tools(apps=apps)
        logger.info(f"Loaded {len(tools)} Composio tools for department={department}")
        return tools
    except Exception as e:
        logger.warning(f"Failed to load Composio tools for {department}: {e}")
        return []
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_tools.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/tools.py backend/tests/test_agents_tools.py
git commit -m "feat: add Composio tool configuration per department"
```

---

## Task 3: Agent Prompts Module

**Files:**
- Create: `backend/agents/prompts.py`

- [ ] **Step 1: Create prompts module**

Create `backend/agents/prompts.py`:

```python
"""Agent instruction strings per department.

These are the ADK agent `instruction` fields — longer and more detailed
than the V1 system prompts because ADK agents use them as their core
behavioral guide across multi-step tool-calling loops.
"""

AGENT_INSTRUCTIONS: dict[str, str] = {
    "admin": """You are Triton Admin AI — a strategic advisor for leadership, HR, and organizational planning.

Tone: Professional, HR-aware, policy-driven, and strategic.
Focus: Internal communications, policy drafting, employee analytics, change management, and organizational planning.

Capabilities:
- Draft and refine internal communications (emails, announcements, memos)
- Build policies and company-wide initiatives
- Summarize reports, meetings, and documents
- Analyze employee feedback and engagement data
- Assist with change management planning

You have access to HR systems, Google Docs, Email, and internal databases via connected tools.
When the user asks you to check, find, or do something — USE your tools. Don't guess.
Always consider legal and compliance implications.
Be concise but thorough in strategic recommendations.
When you complete actions, report what you did with links where available.""",

    "sales": """You are Triton Sales AI — a revenue-focused advisor for sales teams.

Tone: Revenue-driven, persuasive, data-backed, and action-oriented.
Focus: Sales forecasting, CRM insights, outreach messaging, objection handling, and customer strategy.

Capabilities:
- Access CRM data (HubSpot) for pipeline, deals, contacts
- Draft sales emails and outreach sequences
- Analyze pipeline and performance metrics
- Provide objection handling strategies
- Identify at-risk deals and suggest recovery strategies

You have access to CRM, Email, Sheets, Calendar, and Drive via connected tools.
When the user asks about their pipeline, deals, or clients — USE your tools to fetch real data.
Always prioritize by deal value and urgency.
When you complete actions, report what you did with links where available.""",

    "operations": """You are Triton Operations AI — a process optimization specialist.

Tone: Process-oriented, efficient, clear, and practical.
Focus: SOPs, workflow optimization, operational checklists, bottleneck analysis, and internal surveys.

Capabilities:
- Create and optimize Standard Operating Procedures (SOPs)
- Manage tickets and workflows (Jira)
- Generate operational reports and performance summaries
- Design internal surveys and feedback loops
- Troubleshoot operational issues systematically

You have access to Jira, Google Sheets, Docs, Drive, and Forms via connected tools.
When the user asks about tickets, workflows, or processes — USE your tools to fetch real data.
Provide clear, actionable checklists.
When you complete actions, report what you did with links where available.""",

    "finance": """You are Triton Finance AI — a financial analysis and planning specialist.

Tone: Analytical, precise, compliance-aware, and data-driven.
Focus: Budgeting, financial forecasting, P&L analysis, expense tracking, audits, and regulatory compliance.

Capabilities:
- Analyze financial statements, budgets, and expense reports
- Create financial forecasts and projections
- Help with audit preparation and compliance documentation
- Track and optimize expenses across departments
- Prepare executive-ready financial summaries

You have access to Google Sheets, Drive, Docs, and Email via connected tools.
When the user asks about budgets, reports, or financial data — USE your tools to fetch real data.
Always double-check numbers and cite sources.
When you complete actions, report what you did with links where available.""",

    "executive": """You are Triton Executive AI — a C-suite strategic intelligence advisor.

Tone: High-level, visionary, concise, and cross-functional.
Focus: KPI dashboards, board preparation, cross-department insights, strategic planning, and M&A analysis.

Capabilities:
- Synthesize data from ALL departments (Sales pipeline, Finance P&L, Ops metrics, HR data)
- Prepare board meeting materials and presentations
- Track and analyze company-wide KPIs
- Provide strategic recommendations backed by data
- Assist with M&A analysis and competitive intelligence

You have CROSS-DEPARTMENT access to all tools: CRM, Email, Sheets, Drive, Docs, Jira, Calendar.
When the user asks for insights — USE your tools to pull data from multiple sources and synthesize.
Focus on high-impact, big-picture thinking.
When you complete actions, report what you did with links where available.""",
}


AGENT_DESCRIPTIONS: dict[str, str] = {
    "admin": "Admin AI — strategic advisor for leadership, HR, and organizational planning",
    "sales": "Sales AI — revenue-focused advisor for sales teams",
    "operations": "Operations AI — process optimization specialist",
    "finance": "Finance AI — financial analysis and planning specialist",
    "executive": "Executive AI — C-suite strategic intelligence advisor with cross-department access",
}


def get_agent_instruction(department: str) -> str:
    """Get the ADK agent instruction for a department."""
    return AGENT_INSTRUCTIONS.get(department, AGENT_INSTRUCTIONS["admin"])


def get_agent_description(department: str) -> str:
    """Get the ADK agent description for a department."""
    return AGENT_DESCRIPTIONS.get(department, AGENT_DESCRIPTIONS["admin"])
```

- [ ] **Step 2: Commit**

```bash
git add backend/agents/prompts.py
git commit -m "feat: add ADK agent instruction prompts per department"
```

---

## Task 4: Create the 5 Department Agents

**Files:**
- Create: `backend/agents/admin_agent.py`
- Create: `backend/agents/sales_agent.py`
- Create: `backend/agents/ops_agent.py`
- Create: `backend/agents/finance_agent.py`
- Create: `backend/agents/executive_agent.py`

- [ ] **Step 1: Create admin agent**

Create `backend/agents/admin_agent.py`:

```python
"""Admin department ADK agent."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools

admin_agent = Agent(
    name="admin_agent",
    model=AGENT_MODEL,
    description=get_agent_description("admin"),
    instruction=get_agent_instruction("admin"),
    tools=get_composio_tools("admin"),
)
```

- [ ] **Step 2: Create sales agent**

Create `backend/agents/sales_agent.py`:

```python
"""Sales department ADK agent."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools

sales_agent = Agent(
    name="sales_agent",
    model=AGENT_MODEL,
    description=get_agent_description("sales"),
    instruction=get_agent_instruction("sales"),
    tools=get_composio_tools("sales"),
)
```

- [ ] **Step 3: Create operations agent**

Create `backend/agents/ops_agent.py`:

```python
"""Operations department ADK agent."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools

ops_agent = Agent(
    name="ops_agent",
    model=AGENT_MODEL,
    description=get_agent_description("operations"),
    instruction=get_agent_instruction("operations"),
    tools=get_composio_tools("operations"),
)
```

- [ ] **Step 4: Create finance agent**

Create `backend/agents/finance_agent.py`:

```python
"""Finance department ADK agent."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools

finance_agent = Agent(
    name="finance_agent",
    model=AGENT_MODEL,
    description=get_agent_description("finance"),
    instruction=get_agent_instruction("finance"),
    tools=get_composio_tools("finance"),
)
```

- [ ] **Step 5: Create executive agent**

Create `backend/agents/executive_agent.py`:

```python
"""Executive department ADK agent — has cross-department tool access."""

from google.adk.agents import Agent

from agents.config import AGENT_MODEL
from agents.prompts import get_agent_instruction, get_agent_description
from agents.tools import get_composio_tools

executive_agent = Agent(
    name="executive_agent",
    model=AGENT_MODEL,
    description=get_agent_description("executive"),
    instruction=get_agent_instruction("executive"),
    tools=get_composio_tools("executive"),
)
```

- [ ] **Step 6: Commit**

```bash
git add backend/agents/admin_agent.py backend/agents/sales_agent.py backend/agents/ops_agent.py backend/agents/finance_agent.py backend/agents/executive_agent.py
git commit -m "feat: create 5 department ADK agents"
```

---

## Task 5: Agent Router

**Files:**
- Create: `backend/agents/router.py`
- Test: `backend/tests/test_agents_router.py`

- [ ] **Step 1: Write test for routing**

Create `backend/tests/test_agents_router.py`:

```python
"""Tests for agent department routing."""

import pytest
from unittest.mock import patch, MagicMock


# Mock the ADK Agent class before importing router
@pytest.fixture(autouse=True)
def mock_adk_agent(monkeypatch):
    """Mock google.adk.agents.Agent so tests don't need real Gemini."""
    mock_agent_cls = MagicMock()
    mock_module = MagicMock()
    mock_module.Agent = mock_agent_cls
    monkeypatch.setitem(
        __import__("sys").modules, "google.adk.agents", mock_module
    )
    # Also mock composio so agent modules don't fail on import
    mock_composio = MagicMock()
    mock_composio.ComposioToolSet.return_value.get_tools.return_value = []
    monkeypatch.setitem(
        __import__("sys").modules, "composio", mock_composio
    )


def test_get_agent_for_known_departments():
    """Each valid department should return a non-None agent."""
    from agents.router import get_agent_for_department

    for dept in ["admin", "sales", "operations", "finance", "executive"]:
        agent = get_agent_for_department(dept)
        assert agent is not None, f"No agent for {dept}"


def test_get_agent_for_unknown_department_returns_admin():
    """Unknown department should fall back to admin agent."""
    from agents.router import get_agent_for_department

    agent = get_agent_for_department("nonexistent")
    assert agent is not None


def test_all_agents_are_distinct():
    """Each department should have its own agent instance."""
    from agents.router import DEPARTMENT_AGENTS

    agents = list(DEPARTMENT_AGENTS.values())
    # Check that we have 5 distinct agents
    assert len(agents) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_router.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement router**

Create `backend/agents/router.py`:

```python
"""Department-to-agent routing.

Direct routing: user's department determines which ADK agent handles their request.
No LLM-based classification needed — the department is known from JWT claims.
"""

from google.adk.agents import Agent

from agents.admin_agent import admin_agent
from agents.sales_agent import sales_agent
from agents.ops_agent import ops_agent
from agents.finance_agent import finance_agent
from agents.executive_agent import executive_agent

DEPARTMENT_AGENTS: dict[str, Agent] = {
    "admin": admin_agent,
    "sales": sales_agent,
    "operations": ops_agent,
    "finance": finance_agent,
    "executive": executive_agent,
}


def get_agent_for_department(department: str) -> Agent:
    """Get the ADK agent for a department. Falls back to admin."""
    return DEPARTMENT_AGENTS.get(department, admin_agent)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_router.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/router.py backend/tests/test_agents_router.py
git commit -m "feat: add department-to-agent routing"
```

---

## Task 6: Agent Runner (FastAPI-to-ADK Bridge)

**Files:**
- Create: `backend/agents/runner.py`
- Test: `backend/tests/test_agents_runner.py`

This is the core module that bridges the existing FastAPI chat route to ADK agents.

- [ ] **Step 1: Write test for runner**

Create `backend/tests/test_agents_runner.py`:

```python
"""Tests for ADK agent runner — FastAPI bridge."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_build_context_with_summary_and_memory():
    """Context should include session summary and memory when available."""
    from agents.runner import _build_context

    context = _build_context(
        session_summary="User was working on Q2 budget review.",
        memory_context="User prefers bullet points. Working on APAC expansion.",
    )
    assert "Q2 budget review" in context
    assert "APAC expansion" in context


def test_build_context_empty_when_no_data():
    """Context should be empty string when no summary or memory."""
    from agents.runner import _build_context

    context = _build_context(session_summary=None, memory_context="")
    assert context == ""


def test_format_to_structured_response_plain_text():
    """Plain text should be wrapped in structured format."""
    from agents.runner import _format_to_structured_response

    result = _format_to_structured_response("Hello, how can I help?")
    assert result["sections"][0]["content"] == "Hello, how can I help?"
    assert isinstance(result["title"], str)
    assert isinstance(result["summary"], str)
    assert isinstance(result["key_takeaways"], list)


def test_format_to_structured_response_empty():
    """Empty response should return fallback."""
    from agents.runner import _format_to_structured_response

    result = _format_to_structured_response("")
    assert result["sections"][0]["content"] == "No response received from AI."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_runner.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement runner**

Create `backend/agents/runner.py`:

```python
"""FastAPI-to-ADK bridge.

Bridges the existing chat route to ADK agent execution:
1. Builds context from session summary + mem0 memory
2. Runs the ADK agent with the user's message + context
3. Formats the agent's response into the structured JSON the frontend expects
"""

import logging
from typing import Optional

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from services.memory_service import search_memory, add_memory

logger = logging.getLogger(__name__)

# Shared session service — ADK manages its own in-memory session state
_session_service = InMemorySessionService()


def _build_context(
    session_summary: Optional[str],
    memory_context: str,
) -> str:
    """Build context prefix from session summary and memory."""
    parts = []
    if session_summary:
        parts.append(f"[Previous session context]: {session_summary}")
    if memory_context:
        parts.append(f"[User memory]: {memory_context}")
    return "\n".join(parts)


def _build_memory_context(user_id: str, department: str, query: str) -> str:
    """Search mem0 for relevant past memories and format as context string."""
    memories = search_memory(user_id, department, query, limit=5)
    if not memories:
        return ""

    memory_texts = []
    for mem in memories:
        if isinstance(mem, dict):
            text = mem.get("memory", mem.get("text", str(mem)))
        else:
            text = str(mem)
        # Basic sanitization
        text = text.replace("\x00", "").strip()[:500]
        memory_texts.append(f"  - {text}")

    return "\n".join(memory_texts)


def _format_to_structured_response(text: str) -> dict:
    """Wrap agent output text in the structured response format the frontend expects.

    The frontend renders: {title, summary, sections[], key_takeaways[]}
    """
    if not text or not text.strip():
        text = "No response received from AI."

    return {
        "title": "",
        "summary": "",
        "sections": [{"heading": "", "content": text}],
        "key_takeaways": [],
    }


async def run_agent(
    agent: Agent,
    user_id: str,
    department: str,
    message: str,
    session_id: str,
    conversation_history: list[dict],
    session_summary: Optional[str] = None,
) -> dict:
    """Execute an ADK agent with full context and return structured response.

    Args:
        agent: The department's ADK Agent instance
        user_id: Current user's ID
        department: User's department
        message: The user's message (may include document context)
        session_id: Chat session ID
        conversation_history: Previous messages in this session
        session_summary: Rolling AI-generated summary of session (if exists)

    Returns:
        Structured dict: {title, summary, sections[], key_takeaways[]}
    """
    # Build memory context
    memory_context = _build_memory_context(user_id, department, message)

    # Build full context prefix
    context = _build_context(session_summary, memory_context)

    # Prepend context to the user message if we have any
    full_message = f"{context}\n\n{message}" if context else message

    try:
        # Create ADK runner
        runner = Runner(
            agent=agent,
            app_name="triton",
            session_service=_session_service,
        )

        # Build the user content
        user_content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=full_message)],
        )

        # Run the agent — this handles multi-step tool calling automatically
        response_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            # Collect the final agent response text
            if event.is_final_response():
                for part in event.content.parts:
                    if part.text:
                        response_text += part.text

    except Exception as e:
        logger.error(f"ADK agent execution failed: {e}", exc_info=True)
        response_text = "I'm sorry, I encountered an error processing your request. Please try again."

    # Store conversation in mem0 memory
    try:
        add_memory(
            user_id=user_id,
            department=department,
            messages=[
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text[:2000]},
            ],
        )
    except Exception as e:
        logger.warning(f"Failed to store memory: {e}")

    return _format_to_structured_response(response_text)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_agents_runner.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/runner.py backend/tests/test_agents_runner.py
git commit -m "feat: add ADK agent runner (FastAPI-to-ADK bridge)"
```

---

## Task 7: Session Summary Service

**Files:**
- Create: `backend/services/summary_service.py`
- Modify: `backend/db/models.py:42-59`
- Modify: `backend/db/database.py` (add migration)
- Test: `backend/tests/test_summary_service.py`

- [ ] **Step 1: Add columns to ChatSession model**

In `backend/db/models.py`, add two columns to the `ChatSession` class after the `document_name` field (after line 50):

```python
    session_summary = Column(Text, nullable=True)
    summary_msg_count = Column(Integer, default=0)
```

- [ ] **Step 2: Add auto-migration for new columns**

In `backend/db/database.py`, add a migration function (following the existing `_migrate_user_connectors` pattern). Add this function and call it from `init_db()`:

```python
def _migrate_session_summary():
    """Add session_summary and summary_msg_count columns if missing."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("chat_sessions")]

    with engine.connect() as conn:
        if "session_summary" not in columns:
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN session_summary TEXT"))
            conn.commit()
        if "summary_msg_count" not in columns:
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN summary_msg_count INTEGER DEFAULT 0"))
            conn.commit()
```

Call `_migrate_session_summary()` inside the existing `init_db()` function, after the other migration calls.

- [ ] **Step 3: Write test for summary service**

Create `backend/tests/test_summary_service.py`:

```python
"""Tests for session summary service."""

import pytest


def test_should_update_summary_returns_false_below_threshold():
    """Should not update summary when fewer than 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=15, last_summary_count=10) is False


def test_should_update_summary_returns_true_at_threshold():
    """Should update summary at exactly 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=20, last_summary_count=10) is True


def test_should_update_summary_returns_true_above_threshold():
    """Should update summary when more than 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=25, last_summary_count=10) is True


def test_should_update_summary_first_time():
    """Should update summary on first check after 10 messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=10, last_summary_count=0) is True


def test_should_update_summary_not_on_first_few():
    """Should not update with only a few messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=5, last_summary_count=0) is False
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_summary_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 5: Implement summary service**

Create `backend/services/summary_service.py`:

```python
"""Session summary service — auto-generates rolling summaries every 10 messages.

The summary provides long-term context when a user returns to a session,
so the agent knows what was previously discussed without loading all messages.
"""

import logging

import google.genai as genai
from sqlalchemy.orm import Session as DBSession

from agents.config import GEMINI_API_KEY, AGENT_MODEL
from db.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

SUMMARY_THRESHOLD = 10  # Generate/update summary every N new messages


def should_update_summary(current_count: int, last_summary_count: int) -> bool:
    """Check if we should generate/update the session summary."""
    return (current_count - last_summary_count) >= SUMMARY_THRESHOLD


async def update_session_summary(db: DBSession, session_id: str) -> None:
    """Generate or update the rolling session summary if threshold is met.

    Called after each assistant response. Checks if enough new messages
    have accumulated since the last summary, and if so, asks Gemini to
    generate a concise summary of the full conversation.
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return

    # Count messages in session
    msg_count = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).count()

    if not should_update_summary(msg_count, session.summary_msg_count or 0):
        return

    # Fetch all messages for summarization
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    # Format conversation for summarization
    conversation_text = "\n".join(
        f"{m.role}: {m.content[:500]}" for m in messages
    )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=AGENT_MODEL,
            contents=(
                "Summarize this conversation in 3-5 sentences. "
                "Focus on: what the user is working on, key decisions made, "
                "and pending action items.\n\n"
                f"{conversation_text[:8000]}"
            ),
        )
        summary_text = response.text

        session.session_summary = summary_text
        session.summary_msg_count = msg_count
        db.commit()
        logger.info(f"Updated session summary for {session_id} (msgs={msg_count})")

    except Exception as e:
        logger.warning(f"Failed to generate session summary: {e}")
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/test_summary_service.py -v`
Expected: 5 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/db/models.py backend/db/database.py backend/services/summary_service.py backend/tests/test_summary_service.py
git commit -m "feat: add session summary service with auto-generation"
```

---

## Task 8: Update Memory Service (Groq -> Gemini)

**Files:**
- Modify: `backend/services/memory_service.py:25-45`

- [ ] **Step 1: Update Mem0 LLM config from Groq to Gemini**

In `backend/services/memory_service.py`, replace the `config` dict inside `_get_memory()` (lines 25-45):

Replace the LLM section:
```python
            "llm": {
                "provider": "groq",
                "config": {
                    "model": "llama-3.3-70b-versatile",
                    "api_key": settings.GROQ_API_KEY,
                },
            },
```

With:
```python
            "llm": {
                "provider": "google",
                "config": {
                    "model": "gemini-2.5-flash",
                    "api_key": settings.GEMINI_API_KEY,
                },
            },
```

- [ ] **Step 2: Verify memory service still imports cleanly**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -c "from services.memory_service import search_memory, add_memory; print('OK')"`
Expected: `OK` (or a warning about mem0 init if no API key — that's fine)

- [ ] **Step 3: Commit**

```bash
git add backend/services/memory_service.py
git commit -m "feat: switch Mem0 LLM from Groq to Gemini"
```

---

## Task 9: Wire Chat Router to ADK Agents

**Files:**
- Modify: `backend/routers/chat.py`

This is the critical integration step — replacing `chat_completion()` with `run_agent()`.

- [ ] **Step 1: Update imports in chat.py**

In `backend/routers/chat.py`, replace the groq_service imports (line 16-17):

Replace:
```python
from services.groq_service import chat_completion, chat_completion_stream
```

With:
```python
from agents.router import get_agent_for_department
from agents.runner import run_agent
from services.summary_service import update_session_summary
```

- [ ] **Step 2: Update the chat endpoint**

Replace the `chat()` function body (lines 191-248). The key change is replacing `chat_completion()` with `run_agent()` and adding summary updates.

Replace the try/except block that calls `chat_completion` (lines 228-237):

```python
    try:
        structured = chat_completion(
            user_id=user_id,
            department=department,
            message=full_message,
            conversation_history=history[:-1],
            connector_tokens=connector_tokens,
        )
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail="AI service temporarily unavailable")
```

With:
```python
    # Get the ADK agent for this user's department
    agent = get_agent_for_department(department)

    # Get session summary for long-term context
    session = get_session(db, session_id)
    session_summary = session.session_summary if session else None

    try:
        structured = await run_agent(
            agent=agent,
            user_id=user_id,
            department=department,
            message=full_message,
            session_id=session_id,
            conversation_history=history[:-1],
            session_summary=session_summary,
        )
    except Exception as e:
        logger.error(f"Agent execution error: {e}")
        raise HTTPException(status_code=500, detail="AI service temporarily unavailable")
```

After the `add_message(db, session_id, "assistant", flat_markdown)` line (line 241), add:
```python
    # Update session summary if threshold reached
    await update_session_summary(db, session_id)
```

Also remove the unused `connector_tokens` block. The lines fetching `connector_tokens` (lines 222-225) can be removed since Composio handles tool auth now. Remove:
```python
    # Get user's connected connector tokens for MCP integration
    connector_tokens = _get_connector_tokens(db, user_id)
    if connector_tokens:
        logger.info(f"User {user_id} has {len(connector_tokens)} connected connector(s): {list(connector_tokens.keys())}")
```

- [ ] **Step 3: Update the stream endpoint similarly**

In the `chat_stream()` function, replace the `chat_completion_stream()` call inside `event_generator()` with the same ADK agent call pattern:

Replace:
```python
            structured = chat_completion_stream(
                user_id=user_id,
                department=department,
                message=full_message,
                conversation_history=history[:-1],
                connector_tokens=connector_tokens,
            )
```

With:
```python
            agent = get_agent_for_department(department)
            session = get_session(db, session_id)
            session_summary = session.session_summary if session else None

            structured = await run_agent(
                agent=agent,
                user_id=user_id,
                department=department,
                message=full_message,
                session_id=session_id,
                conversation_history=history[:-1],
                session_summary=session_summary,
            )
```

And add after the `add_message` call:
```python
            await update_session_summary(db, session_id)
```

Remove the `connector_tokens` fetch from the stream endpoint as well.

- [ ] **Step 4: Remove unused imports and helpers**

Remove the `_get_connector_tokens()` function and `_refresh_token_if_needed()` function from `chat.py` — Composio handles all tool auth now. Also remove the `httpx` import and `UserConnector` import since they're no longer needed in this file.

Keep them in `connectors.py` where they belong (MintMCP still works as fallback).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/chat.py
git commit -m "feat: wire chat router to ADK agents (replace groq_service)"
```

---

## Task 10: Update main.py Health Check

**Files:**
- Modify: `backend/main.py:104-126`

- [ ] **Step 1: Update deep health check**

In `backend/main.py`, update the deep health check to verify Gemini instead of Groq:

Replace:
```python
    # Groq check
    checks["groq"] = "configured" if settings.GROQ_API_KEY else "not_configured"
```

With:
```python
    # Gemini check
    checks["gemini"] = "configured" if settings.GEMINI_API_KEY else "not_configured"
```

Also update the FastAPI app description (line 47):
```python
    description="Five-role AI chat platform with Gemini LLM, ADK agents, and Composio tools",
```

- [ ] **Step 2: Commit**

```bash
git add backend/main.py
git commit -m "feat: update health check and app description for V2"
```

---

## Task 11: Update docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add new env vars to docker-compose**

In `docker-compose.yml`, in the `backend` service `environment` section, add:

```yaml
      GEMINI_API_KEY: ${GEMINI_API_KEY:?GEMINI_API_KEY is required}
      COMPOSIO_API_KEY: ${COMPOSIO_API_KEY:-}
```

And change `GROQ_API_KEY` from required to optional (keep for backward compat):
```yaml
      GROQ_API_KEY: ${GROQ_API_KEY:-}
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Gemini/Composio env vars to docker-compose"
```

---

## Task 12: Delete groq_service.py + Final Integration Test

**Files:**
- Delete: `backend/services/groq_service.py`

- [ ] **Step 1: Verify no remaining imports of groq_service**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && grep -r "groq_service" --include="*.py" .`
Expected: Only hits in `groq_service.py` itself (already removed from `chat.py` in Task 9)

- [ ] **Step 2: Delete groq_service.py**

Run: `rm /Users/bhumikasingh/Desktop/polaris/backend/services/groq_service.py`

- [ ] **Step 3: Verify the app imports cleanly**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -c "from agents.router import get_agent_for_department; from agents.runner import run_agent; print('All imports OK')"`

- [ ] **Step 4: Run all tests**

Run: `cd /Users/bhumikasingh/Desktop/polaris/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git rm backend/services/groq_service.py
git add -A
git commit -m "feat: remove groq_service.py — fully replaced by ADK agents"
```

---

## Task 13: Update __init__.py exports

**Files:**
- Modify: `backend/agents/__init__.py`

- [ ] **Step 1: Add clean exports to agents package**

Update `backend/agents/__init__.py`:

```python
"""Google ADK multi-agent system for Triton V2.

Usage:
    from agents.router import get_agent_for_department
    from agents.runner import run_agent
"""

from agents.router import get_agent_for_department
from agents.runner import run_agent

__all__ = ["get_agent_for_department", "run_agent"]
```

- [ ] **Step 2: Commit**

```bash
git add backend/agents/__init__.py
git commit -m "feat: finalize agents package exports"
```

---

## Verification Checklist

After all tasks are complete, verify:

1. **App starts**: `cd backend && uvicorn main:app --reload` — no import errors
2. **Health check**: `curl http://localhost:8000/api/health/deep` — shows `gemini: configured`
3. **All tests pass**: `python -m pytest tests/ -v`
4. **Chat works**: POST to `/api/chat` with a valid JWT — gets structured response from Gemini
5. **Department routing**: Login as sales user → gets sales agent; login as finance → gets finance agent
6. **Session summary**: After 10+ messages in a session, `session_summary` column populated
7. **Memory scoping**: Sales user memories don't leak to finance user

---

## Deferred to Follow-Up

These items from the spec are **not** in this plan — they should be separate plans:

1. **PDF Vision (Phase 5)**: Gemini native PDF reading via `genai.upload_file()` — requires changes to `upload.py` and runner
2. **Streaming**: ADK supports async streaming but the current frontend sends the structured response as a single SSE event. True token streaming requires frontend changes.
3. **MintMCP removal**: The connectors router + OAuth flow is kept intact. Composio is additive. Full MintMCP removal is a separate cleanup task after Composio is proven in production.
