"""Tests for OpenRouter agent runner — FastAPI bridge."""

import pytest


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


@pytest.mark.asyncio
async def test_run_agent_with_tool_call():
    """Verify run_agent handles a tool call, executes it, and gets the final response."""
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock OpenAI client response
    mock_response_1 = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc"
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "GMAIL_LIST_MESSAGES"
    mock_tool_call.function.arguments = "{}"
    mock_response_1.choices = [
        MagicMock(message=MagicMock(content=None, tool_calls=[mock_tool_call]))
    ]

    mock_response_2 = MagicMock()
    mock_response_2.choices = [
        MagicMock(message=MagicMock(content="Here are your messages.", tool_calls=None))
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[mock_response_1, mock_response_2]
    )

    # Mock Composio session
    mock_session = MagicMock()
    mock_session.session_id = "mock_session_id"
    mock_exec_result = MagicMock()
    mock_exec_result.data = {"messages": []}
    mock_exec_result.error = None
    mock_session.execute.return_value = mock_exec_result

    mock_composio = MagicMock()
    mock_composio.create.return_value = mock_session

    with patch("agents.runner.AsyncOpenAI", return_value=mock_client), \
         patch("composio.Composio", return_value=mock_composio):
        
        from agents.runner import run_agent
        
        agent_tools = [{"type": "function", "function": {"name": "GMAIL_LIST_MESSAGES"}}]
        
        result = await run_agent(
            agent_instruction="You are a helpful assistant.",
            agent_tools=agent_tools,
            user_id="user_123",
            department="admin",
            message="List my email messages",
            session_id="session_abc",
            conversation_history=[],
        )

        assert result["sections"][0]["content"] == "Here are your messages."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["raw_name"] == "GMAIL_LIST_MESSAGES"
        assert result["tool_calls"][0]["status"] == "success"

        # Verify execute was called with correct args
        mock_session.execute.assert_called_once_with("GMAIL_LIST_MESSAGES", arguments={})


@pytest.mark.asyncio
async def test_run_agent_gates_destructive_tool():
    """Verify run_agent gates destructive tools and raises ConfirmationRequired."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from agents.tools import ConfirmationRequired

    mock_response = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_abc"
    mock_tool_call.type = "function"
    # GMAIL_SEND_EMAIL is destructive
    mock_tool_call.function.name = "GMAIL_SEND_EMAIL"
    mock_tool_call.function.arguments = '{"recipient_email": "x@y.com", "subject": "hi"}'
    mock_response.choices = [
        MagicMock(message=MagicMock(content=None, tool_calls=[mock_tool_call]))
    ]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mock_session = MagicMock()
    mock_session.session_id = "mock_session_id"
    mock_composio = MagicMock()
    mock_composio.create.return_value = mock_session

    with patch("agents.runner.AsyncOpenAI", return_value=mock_client), \
         patch("composio.Composio", return_value=mock_composio):
        
        from agents.runner import run_agent
        
        agent_tools = [{"type": "function", "function": {"name": "GMAIL_SEND_EMAIL"}}]
        
        with pytest.raises(ConfirmationRequired) as excinfo:
            await run_agent(
                agent_instruction="You are a helpful assistant.",
                agent_tools=agent_tools,
                user_id="user_123",
                department="admin",
                message="Send email",
                session_id="session_abc",
                conversation_history=[],
            )

        assert excinfo.value.tool_slug == "GMAIL_SEND_EMAIL"
        assert excinfo.value.tool_args == {"recipient_email": "x@y.com", "subject": "hi"}
        assert excinfo.value.composio_session_id == "mock_session_id"
