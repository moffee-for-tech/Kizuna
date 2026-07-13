"""FastAPI-to-OpenRouter bridge using OpenAI SDK.

Bridges the existing chat route to OpenRouter agent execution:
1. Builds context from session summary
2. Runs the agent with the user's message + context
3. Formats the agent's response into the structured JSON the frontend expects
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from openai import OpenAI, AsyncOpenAI
from agents.config import OPENROUTER_API_KEY, LLM_MODEL
from agents.tools import ConfirmationRequired
from agents.destructive_tools import (
    is_destructive,
    extract_destructive_subtools,
    summarize_for_human,
    build_batch_details,
    build_full_action_details,
    META_EXECUTE_SLUG,
)

MAX_RETRIES = 3

logger = logging.getLogger(__name__)


def _format_to_structured_response(text: str, tool_calls: list[dict] | None = None) -> dict:
    """Wrap agent output text in the structured response format the frontend expects.

    The frontend renders: {title, summary, sections[], key_takeaways[], tool_calls[]}
    """
    if not text or not text.strip():
        text = "No response received from AI."

    return {
        "title": "",
        "summary": "",
        "sections": [{"heading": "", "content": text}],
        "key_takeaways": [],
        "tool_calls": tool_calls or [],
    }


def _humanize_tool_name(raw_name: str) -> str:
    """Convert raw tool name like 'GMAIL_SEND_EMAIL' to 'Agent: Send Email'.

    Internal Composio meta-tools (search, workbench, execute) are hidden
    behind a generic 'Agent: ...' prefix for cleaner UX.
    """
    if not raw_name:
        return "Agent"
    parts = raw_name.split("_", 1)
    if len(parts) == 2:
        toolkit, action = parts
        if toolkit.upper() == "COMPOSIO":
            return f"Agent: {action.replace('_', ' ').title()}"
        return f"{toolkit.title()}: {action.replace('_', ' ').title()}"
    return f"Agent: {raw_name.replace('_', ' ').title()}"


async def run_agent(
    agent_instruction: str,
    agent_tools: list[dict],
    user_id: str,
    department: str,
    message: str,
    session_id: str,
    conversation_history: list[dict],
    session_summary: Optional[str] = None,
) -> dict:
    """Execute an agent with OpenRouter using OpenAI SDK and return structured response."""

    # Build context from session summary
    full_message = message
    if session_summary:
        full_message = f"[Previous session context]: {session_summary}\n\n{message}"

    try:
        client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

        # Build messages with conversation history
        messages = []

        # Add instruction as system message
        if agent_instruction:
            messages.append({"role": "system", "content": agent_instruction})

        # Add conversation history
        for msg in conversation_history:
            messages.append(msg)

        # Add current message
        messages.append({"role": "user", "content": full_message})

        response_text = ""
        tool_calls: list[dict] = []

        # Initialize Composio session if tools are present
        session = None
        composio_session_id = None
        if agent_tools:
            try:
                from composio import Composio
                from agents.tools import DEPARTMENT_TOOLKITS, _SKIP_TOOLKITS
                
                toolkits = DEPARTMENT_TOOLKITS.get(department)
                if toolkits:
                    toolkits = [tk for tk in toolkits if tk not in _SKIP_TOOLKITS]
                
                composio = Composio()
                session = composio.create(user_id=user_id, toolkits=toolkits)
                composio_session_id = session.session_id
            except Exception as e:
                logger.warning(f"Failed to initialize Composio session in runner: {e}")

        async def _create_chat_completion():
            for attempt in range(MAX_RETRIES):
                try:
                    return await client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=messages,
                        tools=agent_tools if agent_tools else None,
                        tool_choice="auto" if agent_tools else None,
                        temperature=0.7,
                    )
                except Exception as e:
                    if "503" in str(e) and attempt < MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.warning(f"OpenRouter 503, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    raise

        # Multi-turn tool execution loop
        max_turns = 10
        for turn in range(max_turns):
            response = await _create_chat_completion()

            message_obj = response.choices[0].message
            
            # Format and append assistant message
            assistant_msg = {"role": "assistant"}
            if message_obj.content:
                assistant_msg["content"] = message_obj.content
            if message_obj.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message_obj.tool_calls
                ]
            messages.append(assistant_msg)

            if not message_obj.tool_calls:
                if message_obj.content:
                    response_text = message_obj.content
                break

            # Process tool calls
            for tool_call in message_obj.tool_calls:
                tool_name = tool_call.function.name
                tool_args_str = tool_call.function.arguments
                try:
                    tool_args = json.loads(tool_args_str)
                except Exception as e:
                    tool_args = {}
                    logger.warning(f"Failed to parse tool arguments: {e}")

                # Check for permission gate (destructive tools)
                slug_upper = tool_name.upper()
                if slug_upper == META_EXECUTE_SLUG:
                    destructive_subs = extract_destructive_subtools(tool_args)
                    if destructive_subs:
                        def _build_batch_description(subs: list) -> str:
                            if len(subs) == 1:
                                s = subs[0]
                                return summarize_for_human(s["tool_slug"], s["arguments"])
                            parts = [summarize_for_human(s["tool_slug"], s["arguments"]) for s in subs]
                            return f"{len(parts)} actions: " + "; ".join(parts)
                        
                        description = _build_batch_description(destructive_subs)
                        raise ConfirmationRequired(
                            tool_slug=tool_name,
                            tool_args=tool_args,
                            composio_session_id=composio_session_id,
                            human_description=description,
                            destructive_subtools=destructive_subs,
                            details=build_batch_details(destructive_subs),
                        )
                elif is_destructive(slug_upper):
                    description = summarize_for_human(slug_upper, tool_args)
                    raise ConfirmationRequired(
                        tool_slug=tool_name,
                        tool_args=tool_args,
                        composio_session_id=composio_session_id,
                        human_description=description,
                        details=[build_full_action_details(slug_upper, tool_args)],
                    )

                if not session:
                    raise RuntimeError("Composio session not initialized but tool execution requested.")

                tool_entry = {
                    "name": _humanize_tool_name(tool_name),
                    "raw_name": tool_name,
                    "status": "running",
                }
                tool_calls.append(tool_entry)

                try:
                    logger.info(f"Executing tool {tool_name} with args {tool_args}")
                    exec_result = session.execute(tool_name, arguments=tool_args)
                    result_data = getattr(exec_result, "data", None)
                    result_error = getattr(exec_result, "error", None)

                    if result_error:
                        tool_entry["status"] = "failed"
                        result_content = json.dumps({"error": result_error}, default=str)
                    else:
                        tool_entry["status"] = "success"
                        result_content = json.dumps(result_data, default=str)
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                    tool_entry["status"] = "failed"
                    result_content = json.dumps({"error": str(e)}, default=str)

                # Append tool response
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content,
                })

    except ConfirmationRequired:
        # Let ConfirmationRequired propagate up to the chat router
        raise
    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        response_text = "I'm sorry, I encountered an error processing your request. Please try again."
        tool_calls = []

    return _format_to_structured_response(response_text, tool_calls)


async def run_agent_streaming(
    agent_instruction: str,
    agent_tools: list[dict],
    user_id: str,
    department: str,
    message: str,
    session_id: str,
    conversation_history: list[dict],
    session_summary: Optional[str] = None,
) -> AsyncIterator[dict]:
    """Streaming version — yields events as the agent executes.

    Yield format:
      {"type": "tool_start", "tool": {name, raw_name, status}}
      {"type": "tool_end", "tool": {name, raw_name, status}}
      {"type": "final", "response": <structured_dict>}
    """
    logger.info(f"run_agent_streaming starting for session={session_id}")

    # Build context from session summary
    full_message = message
    if session_summary:
        full_message = f"[Previous session context]: {session_summary}\n\n{message}"

    response_text = ""
    tool_calls: list[dict] = []

    try:
        client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

        # Build messages with conversation history
        messages = []

        # Add instruction as system message
        if agent_instruction:
            messages.append({"role": "system", "content": agent_instruction})

        # Add conversation history
        for msg in conversation_history:
            messages.append(msg)

        # Add current message
        messages.append({"role": "user", "content": full_message})

        # Initialize Composio session if tools are present
        session = None
        composio_session_id = None
        if agent_tools:
            try:
                from composio import Composio
                from agents.tools import DEPARTMENT_TOOLKITS, _SKIP_TOOLKITS
                
                toolkits = DEPARTMENT_TOOLKITS.get(department)
                if toolkits:
                    toolkits = [tk for tk in toolkits if tk not in _SKIP_TOOLKITS]
                
                composio = Composio()
                session = composio.create(user_id=user_id, toolkits=toolkits)
                composio_session_id = session.session_id
            except Exception as e:
                logger.warning(f"Failed to initialize Composio session in streaming runner: {e}")

        async def _create_chat_completion():
            for attempt in range(MAX_RETRIES):
                try:
                    return await client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=messages,
                        tools=agent_tools if agent_tools else None,
                        tool_choice="auto" if agent_tools else None,
                        temperature=0.7,
                    )
                except Exception as e:
                    if "503" in str(e) and attempt < MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.warning(f"OpenRouter 503, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    raise

        # Multi-turn tool execution loop
        max_turns = 10
        for turn in range(max_turns):
            response = await _create_chat_completion()

            message_obj = response.choices[0].message
            
            # Format and append assistant message
            assistant_msg = {"role": "assistant"}
            if message_obj.content:
                assistant_msg["content"] = message_obj.content
            if message_obj.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message_obj.tool_calls
                ]
            messages.append(assistant_msg)

            if not message_obj.tool_calls:
                if message_obj.content:
                    response_text = message_obj.content
                break

            # Process tool calls
            for tool_call in message_obj.tool_calls:
                tool_name = tool_call.function.name
                tool_args_str = tool_call.function.arguments
                try:
                    tool_args = json.loads(tool_args_str)
                except Exception as e:
                    tool_args = {}
                    logger.warning(f"Failed to parse tool arguments: {e}")

                # Check for permission gate (destructive tools)
                slug_upper = tool_name.upper()
                if slug_upper == META_EXECUTE_SLUG:
                    destructive_subs = extract_destructive_subtools(tool_args)
                    if destructive_subs:
                        def _build_batch_description(subs: list) -> str:
                            if len(subs) == 1:
                                s = subs[0]
                                return summarize_for_human(s["tool_slug"], s["arguments"])
                            parts = [summarize_for_human(s["tool_slug"], s["arguments"]) for s in subs]
                            return f"{len(parts)} actions: " + "; ".join(parts)
                        
                        description = _build_batch_description(destructive_subs)
                        raise ConfirmationRequired(
                            tool_slug=tool_name,
                            tool_args=tool_args,
                            composio_session_id=composio_session_id,
                            human_description=description,
                            destructive_subtools=destructive_subs,
                            details=build_batch_details(destructive_subs),
                        )
                elif is_destructive(slug_upper):
                    description = summarize_for_human(slug_upper, tool_args)
                    raise ConfirmationRequired(
                        tool_slug=tool_name,
                        tool_args=tool_args,
                        composio_session_id=composio_session_id,
                        human_description=description,
                        details=[build_full_action_details(slug_upper, tool_args)],
                    )

                if not session:
                    raise RuntimeError("Composio session not initialized but tool execution requested.")

                tool_entry = {
                    "name": _humanize_tool_name(tool_name),
                    "raw_name": tool_name,
                    "status": "running",
                }
                tool_calls.append(tool_entry)

                # Yield tool start event
                logger.info(f"Yielding tool_start: {tool_entry['name']}")
                yield {"type": "tool_start", "tool": dict(tool_entry)}

                try:
                    logger.info(f"Executing tool {tool_name} with args {tool_args}")
                    exec_result = session.execute(tool_name, arguments=tool_args)
                    result_data = getattr(exec_result, "data", None)
                    result_error = getattr(exec_result, "error", None)

                    if result_error:
                        tool_entry["status"] = "failed"
                        result_content = json.dumps({"error": result_error}, default=str)
                    else:
                        tool_entry["status"] = "success"
                        result_content = json.dumps(result_data, default=str)
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
                    tool_entry["status"] = "failed"
                    result_content = json.dumps({"error": str(e)}, default=str)

                # Yield tool end event
                logger.info(f"Yielding tool_end: {tool_entry['name']} status={tool_entry['status']}")
                yield {"type": "tool_end", "tool": dict(tool_entry)}

                # Append tool response
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content,
                })

    except ConfirmationRequired:
        # Let ConfirmationRequired propagate up to the chat router
        raise
    except Exception as e:
        logger.error(f"Streaming execution failed: {e}", exc_info=True)
        response_text = "I'm sorry, I encountered an error processing your request. Please try again."

    logger.info(f"Yielding final response for session={session_id}")
    yield {"type": "final", "response": _format_to_structured_response(response_text, tool_calls)}
