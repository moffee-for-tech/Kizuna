"""Sessions router with DB persistence."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import SessionCreate, SessionResponse, SessionDetailResponse, ChatMessage
from middleware.rbac import get_current_user
from services.session_store import (
    create_session,
    get_session,
    list_sessions,
    delete_session,
)
from services.prompt_engine import get_prompt_templates
from db.database import get_db

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_new_session(
    data: SessionCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = create_session(
        db=db,
        user_id=current_user["id"],
        department=current_user["department"],
        title=data.title or "New Chat",
    )
    return SessionResponse(
        id=session.id,
        title=session.title,
        department=session.department,
        user_id=session.user_id,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
        message_count=len(session.messages),
        active_skill=session.active_skill,
        lazy_senior_mode=session.lazy_senior_mode,
    )


@router.get("", response_model=list[SessionResponse])
async def get_sessions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all sessions for the current user (department-scoped)."""
    sessions = list_sessions(db, current_user["id"])
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            department=s.department,
            user_id=s.user_id,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            message_count=len(s.messages),
            active_skill=s.active_skill,
            lazy_senior_mode=s.lazy_senior_mode,
        )
        for s in sessions
    ]


@router.get("/templates/prompts")
async def get_templates(current_user: dict = Depends(get_current_user)):
    """Get prompt templates for the current user's department."""
    templates = get_prompt_templates(current_user["department"])
    return {"department": current_user["department"], "templates": templates}


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        department=session.department,
        user_id=session.user_id,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
        message_count=len(session.messages),
        active_skill=session.active_skill,
        lazy_senior_mode=session.lazy_senior_mode,
        messages=[
            ChatMessage(
                role=m.role,
                content=m.content,
                timestamp=m.created_at.isoformat() if m.created_at else "",
            )
            for m in session.messages
        ],
    )


@router.delete("/{session_id}")
async def delete_session_endpoint(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    delete_session(db, session_id)
    return {"detail": "Session deleted"}
