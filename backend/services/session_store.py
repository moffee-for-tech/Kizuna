"""Production-grade session store using SQLAlchemy."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from db.models import ChatSession, ChatMessage


def create_session(db: Session, user_id: str, department: str, title: str = "New Chat") -> ChatSession:
    session = ChatSession(
        id=str(uuid.uuid4()),
        title=title,
        department=department,
        user_id=user_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> Optional[ChatSession]:
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def list_sessions(db: Session, user_id: str) -> list[ChatSession]:
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


def add_message(db: Session, session_id: str, role: str, content: str) -> Optional[ChatMessage]:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return None

    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
    )
    db.add(message)

    # Auto-generate title from first user message
    msg_count = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
    if msg_count == 0 and role == "user":
        session.title = content[:50] + ("..." if len(content) > 50 else "")

    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def delete_session(db: Session, session_id: str) -> bool:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True


def set_session_document(db: Session, session_id: str, document_context: str, document_name: str) -> bool:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return False
    session.document_context = document_context
    session.document_name = document_name
    db.commit()
    return True


def get_session_document(db: Session, session_id: str) -> tuple[str | None, str | None]:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return None, None
    return session.document_context, session.document_name


def get_session_messages(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
