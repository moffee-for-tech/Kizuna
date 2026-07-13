"""Chat router with structured outputs, SSE delivery, and MCP connector integration."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from models import ChatRequest
from middleware.rbac import get_current_user
from agents.router import get_agent_for_department
from agents.runner import run_agent, run_agent_streaming
from agents.tools import ConfirmationRequired
from services.summary_service import update_session_summary
from services.session_store import (
    create_session,
    get_session,
    add_message,
    get_session_messages,
    set_session_document,
    get_session_document,
)
from db.database import get_db
from db.models import PendingAction

PENDING_ACTION_TTL = timedelta(hours=1)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
limiter = Limiter(key_func=get_remote_address)

MAX_MESSAGE_LENGTH = 10_000
MAX_DOCUMENT_LENGTH = 50_000


def sanitize_input(text: str) -> str:
    """Basic input sanitization."""
    text = text.strip()
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH]
    return text


def build_message_with_document(message: str, document_context: str | None, document_name: str | None) -> str:
    """If a document is attached, prepend it as context to the user message."""
    if not document_context:
        return message

    # Truncate very large documents
    doc_text = document_context[:MAX_DOCUMENT_LENGTH]
    name = document_name or "uploaded document"

    return (
        f"[Attached document: {name}]\n"
        f"--- Document content ---\n"
        f"{doc_text}\n"
        f"--- End of document ---\n\n"
        f"{message}"
    )


def _flatten_structured_response(structured: dict) -> str:
    """Convert structured JSON response to readable markdown for DB storage."""
    parts = []
    title = structured.get("title", "")
    if title:
        parts.append(f"## {title}\n")

    summary = structured.get("summary", "")
    if summary:
        parts.append(f"*{summary}*\n")

    for section in structured.get("sections", []):
        heading = section.get("heading", "")
        content = section.get("content", "")
        if heading:
            parts.append(f"### {heading}\n")
        if content:
            parts.append(content + "\n")

    takeaways = structured.get("key_takeaways", [])
    if takeaways:
        parts.append("### Key Takeaways\n")
        for t in takeaways:
            parts.append(f"- {t}")

    return "\n".join(parts)


def _prepare_session(db, user_id, department, session_id):
    """Get or create session and return session_id and history."""
    if not session_id:
        session = create_session(db, user_id, department)
        session_id = session.id
    else:
        session = get_session(db, session_id)
        if not session:
            session = create_session(db, user_id, department)
            session_id = session.id
        elif session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied to this session")
    return session_id


def _resolve_document(db, session_id, request_doc_context, request_doc_name):
    """Resolve document context: use request attachment if provided (and save to session),
    otherwise fall back to session's stored document."""
    if request_doc_context:
        doc_text = request_doc_context[:MAX_DOCUMENT_LENGTH]
        doc_name = request_doc_name or "uploaded document"
        set_session_document(db, session_id, doc_text, doc_name)
        return doc_text, doc_name

    return get_session_document(db, session_id)



@router.post("")
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message and get a structured response."""
    user_id = current_user["id"]
    department = current_user["department"]
    email = current_user.get("email", "")
    name = current_user.get("name", "")
    message = sanitize_input(body.message)

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = _prepare_session(db, user_id, department, body.session_id)

    # Resolve document: save new attachment to session, or load existing one
    doc_context, doc_name = _resolve_document(db, session_id, body.document_context, body.document_name)
    full_message = build_message_with_document(message, doc_context, doc_name)

    # Store only the plain user message in DB (not the PDF blob)
    add_message(db, session_id, "user", message)
    history_msgs = get_session_messages(db, session_id)
    history = [{"role": m.role, "content": m.content} for m in history_msgs]

    # Inject document context into the first system-level history entry for the LLM
    # so it has document awareness without storing it in every message row
    if doc_context and history:
        doc_prefix = build_message_with_document("", doc_context, doc_name)
        history[0] = {"role": history[0]["role"], "content": doc_prefix + history[0]["content"]}

    # Get the agent config for this user's department (per-user Composio tools).
    # Identity is pinned into the agent prompt as defense-in-depth.
    agent_config = get_agent_for_department(department, user_id, email=email, name=name)

    # Get session summary for long-term context
    session = get_session(db, session_id)
    session_summary = session.session_summary if session else None

    try:
        structured = await run_agent(
            agent_instruction=agent_config["instruction"],
            agent_tools=agent_config["tools"],
            user_id=user_id,
            department=department,
            message=full_message,
            session_id=session_id,
            conversation_history=history[:-1],
            session_summary=session_summary,
        )
    except ConfirmationRequired as cr:
        action_id = str(uuid.uuid4())
        pending = PendingAction(
            id=action_id,
            user_id=user_id,
            session_id=session_id,
            tool_slug=cr.tool_slug,
            tool_args=json.dumps(cr.tool_args, default=str),
            human_description=cr.human_description,
            composio_session_id=cr.composio_session_id,
            status="pending",
            expires_at=datetime.utcnow() + PENDING_ACTION_TTL,
        )
        db.add(pending)
        db.commit()
        logger.info(
            "Confirmation required (non-streaming) user_id=%s action_id=%s tool=%s",
            user_id, action_id, cr.tool_slug,
        )
        return {
            "session_id": session_id,
            "department": department,
            "confirmation_required": {
                "action_id": action_id,
                "tool_slug": cr.tool_slug,
                "human_description": cr.human_description,
                "destructive_subtools": cr.destructive_subtools,
                "details": cr.details,
                "expires_at": pending.expires_at.isoformat() + "Z",
            },
        }
    except Exception as e:
        logger.error(f"Agent execution error: {e}")
        raise HTTPException(status_code=500, detail="AI service temporarily unavailable")

    # Flatten to markdown for DB storage
    flat_markdown = _flatten_structured_response(structured)
    add_message(db, session_id, "assistant", flat_markdown)

    # Update session summary if threshold reached
    await update_session_summary(db, session_id)

    return {
        "session_id": session_id,
        "message": flat_markdown,
        "structured": structured,
        "department": department,
    }


@router.post("/stream")
@limiter.limit("30/minute")
async def chat_stream(
    request: Request,
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message and stream the structured response via SSE (section by section)."""
    user_id = current_user["id"]
    department = current_user["department"]
    message = sanitize_input(body.message)

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = _prepare_session(db, user_id, department, body.session_id)

    # Resolve document: save new attachment to session, or load existing one
    doc_context, doc_name = _resolve_document(db, session_id, body.document_context, body.document_name)
    full_message = build_message_with_document(message, doc_context, doc_name)

    # Store only the plain user message in DB (not the PDF blob)
    add_message(db, session_id, "user", message)
    history_msgs = get_session_messages(db, session_id)
    history = [{"role": m.role, "content": m.content} for m in history_msgs]

    # Inject document context into the first history entry for LLM awareness
    if doc_context and history:
        doc_prefix = build_message_with_document("", doc_context, doc_name)
        history[0] = {"role": history[0]["role"], "content": doc_prefix + history[0]["content"]}

    email = current_user.get("email", "")
    name = current_user.get("name", "")

    async def event_generator():
        structured = None
        try:
            logger.info(f"event_generator starting for session={session_id}")
            agent_config = get_agent_for_department(department, user_id, email=email, name=name)
            session = get_session(db, session_id)
            session_summary = session.session_summary if session else None

            logger.info(f"Yielding session event for session={session_id}")
            yield {"event": "session", "data": json.dumps({"session_id": session_id})}

            logger.info(f"Starting run_agent_streaming for session={session_id}")
            async for evt in run_agent_streaming(
                agent_instruction=agent_config["instruction"],
                agent_tools=agent_config["tools"],
                user_id=user_id,
                department=department,
                message=full_message,
                session_id=session_id,
                conversation_history=history[:-1],
                session_summary=session_summary,
            ):
                logger.info(f"Received event type={evt.get('type')} for session={session_id}")
                if evt["type"] == "tool_start":
                    logger.info(f"Yielding tool_start SSE event")
                    yield {"event": "tool_start", "data": json.dumps(evt["tool"])}
                elif evt["type"] == "tool_end":
                    logger.info(f"Yielding tool_end SSE event")
                    yield {"event": "tool_end", "data": json.dumps(evt["tool"])}
                elif evt["type"] == "final":
                    structured = evt["response"]
                    logger.info(f"Yielding structured SSE event")
                    yield {"event": "structured", "data": json.dumps(structured)}

            # Flatten and save to DB
            if structured:
                flat_markdown = _flatten_structured_response(structured)
                add_message(db, session_id, "assistant", flat_markdown)
                await update_session_summary(db, session_id)

            yield {"event": "done", "data": json.dumps({"session_id": session_id})}

        except ConfirmationRequired as cr:
            # Agent tried to invoke a destructive tool. Persist a
            # PendingAction row and emit confirmation_required so the UI
            # can render an Allow/Deny card. The stream ends here; the
            # action only executes after POST /api/chat/confirm/{id}.
            action_id = str(uuid.uuid4())
            pending = PendingAction(
                id=action_id,
                user_id=user_id,
                session_id=session_id,
                tool_slug=cr.tool_slug,
                tool_args=json.dumps(cr.tool_args, default=str),
                human_description=cr.human_description,
                composio_session_id=cr.composio_session_id,
                status="pending",
                expires_at=datetime.utcnow() + PENDING_ACTION_TTL,
            )
            db.add(pending)
            db.commit()
            logger.info(
                "Confirmation required user_id=%s session_id=%s action_id=%s tool=%s",
                user_id, session_id, action_id, cr.tool_slug,
            )
            yield {
                "event": "confirmation_required",
                "data": json.dumps({
                    "action_id": action_id,
                    "tool_slug": cr.tool_slug,
                    "human_description": cr.human_description,
                    "destructive_subtools": cr.destructive_subtools,
                    "details": cr.details,
                    "expires_at": pending.expires_at.isoformat() + "Z",
                }),
            }
            yield {"event": "done", "data": json.dumps({"session_id": session_id})}
        except asyncio.CancelledError:
            # User pressed Stop in the UI (client disconnected). Persist whatever
            # we have so the conversation isn't lost, then let the cancellation
            # propagate so sse_starlette can finalize the connection cleanly.
            logger.info(
                "Stream cancelled by client user_id=%s session_id=%s",
                user_id, session_id,
            )
            if structured:
                try:
                    flat_markdown = _flatten_structured_response(structured)
                    add_message(db, session_id, "assistant", flat_markdown + "\n\n_(stopped by user)_")
                except Exception as save_err:
                    logger.warning(f"Could not persist partial response on stop: {save_err}")
            raise
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {"event": "error", "data": json.dumps({"error": "AI service temporarily unavailable"})}

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Confirmation flow — POST /api/chat/confirm/{action_id}
# ---------------------------------------------------------------------------

class ConfirmActionRequest(BaseModel):
    approved: bool
    # User-edited field values from the permission card. Shape:
    #   - Single action: {"arg_key": "new value", ...}
    #   - Batch action (MULTI_EXECUTE): {"0": {"arg_key": "..."}, "1": {...}}
    #     where keys are stringified sub-action indices
    overrides: dict | None = None


@router.post("/confirm/{action_id}")
@limiter.limit("60/minute")
async def confirm_action(
    request: Request,
    action_id: str,
    body: ConfirmActionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve or deny a pending destructive action queued by the agent.

    On approve: executes the tool against Composio using the stored
    composio_session_id, persists a result message on the chat session,
    and returns a structured response card for the UI to render.

    On deny: marks the action denied, persists a "user denied" message,
    returns a structured "cancelled" card.

    Authorization: the action must belong to the calling user and must
    not be expired. Repeated confirms (already approved/denied) are
    rejected to prevent double-execution.
    """
    user_id = current_user["id"]

    pending: PendingAction | None = (
        db.query(PendingAction).filter(PendingAction.id == action_id).first()
    )
    if pending is None:
        raise HTTPException(status_code=404, detail="Action not found")
    if pending.user_id != user_id:
        # Same defense-in-depth shape as session ownership check.
        raise HTTPException(status_code=403, detail="Access denied to this action")
    if pending.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Action already {pending.status}; cannot re-confirm",
        )
    if pending.expires_at < datetime.utcnow():
        pending.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Action expired; please re-ask the agent")

    logger.info(
        "confirm_action user_id=%s action_id=%s tool=%s approved=%s",
        user_id, action_id, pending.tool_slug, body.approved,
    )

    if not body.approved:
        pending.status = "denied"
        denial_text = f"_(action cancelled by user: {pending.human_description})_"
        add_message(db, pending.session_id, "assistant", denial_text)
        db.commit()
        return {
            "session_id": pending.session_id,
            "structured": {
                "title": "",
                "summary": "",
                "sections": [{"heading": "Cancelled", "content": denial_text}],
                "key_takeaways": [],
                "tool_calls": [],
            },
        }

    # ---- Approve: execute the tool directly via Composio ----
    try:
        from composio import Composio
        from agents.destructive_tools import apply_overrides

        composio = Composio()
        # Re-use the same Composio session that was bound to the agent at
        # the moment the request was gated. Composio's session is
        # user-scoped server-side, so this carries the correct identity.
        session = composio.tool_router.use(pending.composio_session_id)
        args = json.loads(pending.tool_args)

        # Apply user-edited field values from the permission card.
        if body.overrides:
            if pending.tool_slug.upper() == "COMPOSIO_MULTI_EXECUTE_TOOL":
                # Batch path: overrides keyed by stringified sub-action index.
                tools_list = args.get("tools", [])
                for idx_str, sub_overrides in body.overrides.items():
                    if not isinstance(sub_overrides, dict):
                        continue
                    try:
                        idx = int(idx_str)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= idx < len(tools_list):
                        sub = tools_list[idx]
                        sub["arguments"] = apply_overrides(sub.get("arguments", {}) or {}, sub_overrides)
                args["tools"] = tools_list
            else:
                args = apply_overrides(args, body.overrides)
            logger.info(
                "confirm_action user_id=%s action_id=%s applied_overrides=true",
                user_id, action_id,
            )

        exec_result = session.execute(pending.tool_slug, arguments=args)
        # SessionExecuteResponse has .data, .error
        result_payload = {
            "data": getattr(exec_result, "data", None),
            "error": getattr(exec_result, "error", None),
        }
        pending.result = json.dumps(result_payload, default=str)
        pending.status = "approved"

        success = result_payload.get("error") is None
        if success:
            content = f"✓ Done — {pending.human_description}"
            heading = "Completed"
        else:
            content = f"✗ Failed — {pending.human_description}\n\nError: {result_payload['error']}"
            heading = "Failed"

        add_message(db, pending.session_id, "assistant", content)
        db.commit()

        return {
            "session_id": pending.session_id,
            "structured": {
                "title": "",
                "summary": "",
                "sections": [{"heading": heading, "content": content}],
                "key_takeaways": [],
                "tool_calls": [{
                    "name": pending.tool_slug.replace("_", " ").title(),
                    "raw_name": pending.tool_slug,
                    "status": "success" if success else "failed",
                }],
            },
        }

    except Exception as e:
        logger.error(
            "tool_exec_failed user_id=%s action_id=%s tool=%s error=%s",
            user_id, action_id, pending.tool_slug, e,
        )
        # Don't lose the pending row; leave status=pending so user can retry
        # manually if it was a transient failure, but surface the error.
        raise HTTPException(
            status_code=502,
            detail=f"Tool execution failed: {type(e).__name__}: {e}",
        )
