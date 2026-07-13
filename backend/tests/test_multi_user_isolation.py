"""Multi-user isolation tests.

These tests guard against the cross-user data leak class (Marissa/Chaz incident,
2026-05-17): two users in the same department, each with their own Composio
OAuth connections, must NEVER share Composio session_ids, tool objects, or
have their tool calls audit-logged under the wrong user_id.
"""

import logging
from unittest.mock import MagicMock, patch

import composio  # noqa: F401


def _make_fake_session(session_id: str, n_tools: int = 2):
    """Build a fake Composio session whose .tools() returns FunctionTool-shaped
    objects (object with a `.func` attribute) — matches what the real SDK returns."""

    class _FakeTool:
        def __init__(self, name):
            def _run(**kwargs):
                return {"ok": True, "name": name, "session": session_id}
            _run.__name__ = name
            _run.__doc__ = f"fake tool {name}"
            self.func = _run

    session = MagicMock()
    session.session_id = session_id
    session.tools.return_value = [_FakeTool(f"TOOL_{i}") for i in range(n_tools)]
    return session


def test_no_cache_two_users_get_distinct_tool_objects(monkeypatch):
    """Regression: the old _tools_cache could keep one user's tool objects alive
    and (per hypothesis) leak their composio session binding. Verify every call
    mints a fresh Composio session and fresh tool objects."""
    monkeypatch.setattr("agents.tools.COMPOSIO_API_KEY", "fake-key")

    sessions_minted = []

    def _fake_create(**kwargs):
        sid = f"sess-{kwargs['user_id']}-{len(sessions_minted)}"
        s = _make_fake_session(sid)
        sessions_minted.append((kwargs["user_id"], sid))
        return s

    fake_composio = MagicMock()
    fake_composio.create.side_effect = _fake_create

    with patch("composio.Composio", return_value=fake_composio):
        from agents.tools import get_composio_tools

        tools_a = get_composio_tools("user-A", "admin")
        tools_b = get_composio_tools("user-B", "admin")
        tools_a_again = get_composio_tools("user-A", "admin")

    assert len(sessions_minted) == 3, "Cache must be removed — every call must mint a fresh session"
    assert sessions_minted[0][0] == "user-A"
    assert sessions_minted[1][0] == "user-B"
    assert sessions_minted[2][0] == "user-A"

    # Sessions for different users must be distinct
    assert sessions_minted[0][1] != sessions_minted[1][1]
    # Even the same user gets a fresh session on the next call
    assert sessions_minted[0][1] != sessions_minted[2][1]

    # No shared tool object identity across users
    a_ids = {id(t) for t in tools_a}
    b_ids = {id(t) for t in tools_b}
    assert not (a_ids & b_ids), "Tool objects must not be reused across users"


def test_audit_log_records_user_id_and_session_id_on_invocation(monkeypatch, caplog):
    """Every tool invocation must emit an audit log line carrying the exact
    (user_id, composio_session_id) that the tool was bound to at creation time."""
    monkeypatch.setattr("agents.tools.COMPOSIO_API_KEY", "fake-key")

    fake_session = _make_fake_session("sess-abc-123", n_tools=1)
    fake_composio = MagicMock()
    fake_composio.create.return_value = fake_session

    with patch("composio.Composio", return_value=fake_composio):
        from agents.tools import get_composio_tools

        with caplog.at_level(logging.INFO, logger="triton.audit.composio"):
            tools = get_composio_tools("user-A", "admin")
            assert len(tools) == 1
            # Invoke the wrapped tool the same way ADK would
            result = tools[0].func()

    assert result["session"] == "sess-abc-123"

    msgs = [r.getMessage() for r in caplog.records if r.name == "triton.audit.composio"]
    assert any("session_create" in m and "user-A" in m and "sess-abc-123" in m for m in msgs), \
        f"Missing session_create audit log: {msgs}"
    assert any("tool_call" in m and "user-A" in m and "sess-abc-123" in m for m in msgs), \
        f"Missing tool_call audit log with bound user/session: {msgs}"
    assert any("tool_done" in m and "user-A" in m and "status=ok" in m for m in msgs), \
        f"Missing tool_done audit log: {msgs}"


def test_disable_composio_killswitch(monkeypatch):
    """DISABLE_COMPOSIO=true must short-circuit and return no tools (emergency
    containment — must work without code changes)."""
    monkeypatch.setattr("agents.tools.COMPOSIO_API_KEY", "fake-key")
    monkeypatch.setenv("DISABLE_COMPOSIO", "true")

    from agents.tools import get_composio_tools
    assert get_composio_tools("user-A", "admin") == []


def test_agent_prompt_pins_acting_user_identity():
    """The agent instruction must include an explicit identity preamble naming
    the acting user, so the LLM can refuse cross-user data forwarding even if
    a tool binding is somehow wrong (defense in depth)."""
    from agents.prompts import get_agent_instruction

    instruction = get_agent_instruction(
        "admin",
        user_id="user-A-uuid",
        email="chaz@example.com",
        name="Chaz",
    )

    assert "user-A-uuid" in instruction
    assert "chaz@example.com" in instruction
    assert "Chaz" in instruction
    # Must include a refusal directive
    assert "MUST NOT" in instruction or "STOP" in instruction


def test_agent_prompt_without_identity_still_has_destructive_actions_policy():
    """Even when no acting-user identity is provided (legacy callers), the
    destructive-actions policy must still be present and tell the agent
    that the platform shows a permission card."""
    from agents.prompts import get_agent_instruction, AGENT_INSTRUCTIONS

    instruction = get_agent_instruction("admin")
    assert "[DESTRUCTIVE ACTIONS" in instruction
    assert AGENT_INSTRUCTIONS["admin"] in instruction


def test_agent_prompt_describes_platform_permission_card():
    """The agent must be told the PLATFORM handles approval via a card,
    and that it should NOT also ask 'reply yes' in chat (which double-
    prompts the user: they type yes AND have to click Allow). Still must
    distinguish destructive vs read-only and handle batches."""
    from agents.prompts import get_agent_instruction

    instruction = get_agent_instruction(
        "admin", user_id="u", email="e@x.com", name="N"
    )

    assert "[DESTRUCTIVE ACTIONS" in instruction
    # Must tell the LLM the platform handles approval (not the LLM)
    assert "permission card" in instruction.lower() or "Allow" in instruction
    # Must discourage the redundant text confirmation prompt
    assert "do not" in instruction.lower() or "redundant" in instruction.lower()
    # Read-only carve-out still present
    assert "Read-only" in instruction or "read-only" in instruction
    # Batch handling still present
    assert "MULTI_EXECUTE" in instruction or "batch" in instruction.lower()
