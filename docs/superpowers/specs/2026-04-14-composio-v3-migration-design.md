# Composio v3 SDK Migration — Design Spec

**Date:** 2026-04-14
**Branch:** security-audit
**Goal:** Migrate from deprecated Composio v1/v2 (`ComposioToolSet`) to v3 SDK (`Composio` + `GoogleAdkProvider`) with per-user tool sessions.

---

## Problem

Current code uses the deprecated `ComposioToolSet` API. Tools are loaded once at module import time as singletons — no per-user scoping. The v3 SDK requires `composio.create(user_id=...)` to create per-user sessions with authed tools.

## Approach

**Agent Factory pattern (Approach C):** Replace singleton agents with factory functions that create a fresh `Agent` per request with the user's Composio tools. This enables cross-tool orchestration (e.g., "what's my todo?" queries that span Gmail, Calendar, Sheets).

**MintMCP kept as fallback.** The `connectors.py` OAuth flow is untouched.

---

## Changes

### 1. `backend/requirements.txt`

Replace:
```
composio-core>=0.7.0
```
With:
```
composio>=1.0.0
composio-google-adk>=1.0.0
```

### 2. `backend/agents/tools.py` — Composio v3 Session Manager

- Replace `ComposioToolSet` with `Composio(provider=GoogleAdkProvider())`
- `get_composio_tools(user_id, department)` creates a per-user session and returns ADK-native tools scoped by department toolkits
- Rename `DEPARTMENT_TOOLS` → `DEPARTMENT_TOOLKITS` (v3 terminology)
- Add `google_chat` to all departments
- Ensure consistent Google suite (Gmail, Chat, Calendar, Drive, Sheets, Docs) across all departments
- Department-specific extras: sales/exec get HubSpot, ops/exec get Jira, ops gets Google Forms

```python
DEPARTMENT_TOOLKITS = {
    "admin": ["gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs"],
    "sales": ["hubspot", "gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs"],
    "operations": ["jira", "gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs", "google_forms"],
    "finance": ["gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs"],
    "executive": ["hubspot", "jira", "gmail", "google_chat", "google_calendar", "google_drive", "google_sheets", "google_docs"],
}
```

### 3. `backend/agents/*_agent.py` — Agent Factories

All 5 agent files (`admin_agent.py`, `sales_agent.py`, `ops_agent.py`, `finance_agent.py`, `executive_agent.py`) change from module-level singletons to factory functions:

```python
# Before
admin_agent = Agent(name="admin_agent", model=..., instruction=..., tools=get_composio_tools("admin"))

# After
def create_admin_agent(user_id: str) -> Agent:
    tools = get_composio_tools(user_id, "admin")
    return Agent(name="admin_agent", model=AGENT_MODEL, instruction=..., tools=tools)
```

### 4. `backend/agents/router.py` — Factory Router

Replace singleton lookup dict with factory dispatch:

```python
DEPARTMENT_FACTORIES = {
    "admin": create_admin_agent,
    "sales": create_sales_agent,
    "operations": create_ops_agent,
    "finance": create_finance_agent,
    "executive": create_executive_agent,
}

def get_agent_for_department(department: str, user_id: str) -> Agent:
    factory = DEPARTMENT_FACTORIES.get(department, create_admin_agent)
    return factory(user_id)
```

### 5. `backend/agents/__init__.py`

Update exports to reflect new function signatures.

### 6. `backend/routers/chat.py`

Pass `user_id` to `get_agent_for_department`:

```python
# Before
agent = get_agent_for_department(department)

# After
agent = get_agent_for_department(department, user_id)
```

Both `chat()` and `chat_stream()` endpoints need this update.

### 7. `backend/agents/config.py`

No changes needed — `COMPOSIO_API_KEY` and `AGENT_MODEL` stay the same.

### 8. Tests

Update all agent tests to:
- Mock `composio` and `composio_google_adk` instead of old `composio` imports
- Call factory functions with a `user_id` parameter
- Update `test_agents_tools.py` to test new `get_composio_tools(user_id, department)` signature
- Update `test_agents_router.py` to test `get_agent_for_department(department, user_id)`

---

## Files Changed

| File | Change |
|------|--------|
| `backend/requirements.txt` | `composio-core` → `composio` + `composio-google-adk` |
| `backend/agents/tools.py` | Full rewrite — v3 SDK, per-user sessions |
| `backend/agents/admin_agent.py` | Singleton → factory function |
| `backend/agents/sales_agent.py` | Singleton → factory function |
| `backend/agents/ops_agent.py` | Singleton → factory function |
| `backend/agents/finance_agent.py` | Singleton → factory function |
| `backend/agents/executive_agent.py` | Singleton → factory function |
| `backend/agents/router.py` | Singleton dict → factory dispatch, add `user_id` param |
| `backend/agents/__init__.py` | Update exports |
| `backend/routers/chat.py` | Pass `user_id` to `get_agent_for_department` |
| `backend/tests/test_agents_tools.py` | Update for new signature |
| `backend/tests/test_agents_router.py` | Update for new signature |

## Files NOT Changed

| File | Reason |
|------|--------|
| `backend/routers/connectors.py` | MintMCP kept as fallback |
| `backend/agents/runner.py` | Already receives `Agent` object, no change needed |
| `backend/agents/prompts.py` | Unchanged |
| `backend/agents/config.py` | Unchanged |
| `backend/services/*` | Unchanged |
