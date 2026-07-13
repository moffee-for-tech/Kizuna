"""SQLAlchemy ORM models for Triton."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    ForeignKey,
    Integer,
    Index,
)
from sqlalchemy.orm import relationship
from db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    department = Column(String(50), nullable=False, index=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 2FA (TOTP) — secret is Fernet-encrypted at rest, backup codes are PBKDF2-hashed
    totp_secret_encrypted = Column(Text, nullable=True)
    totp_enabled = Column(Integer, default=0)
    totp_backup_codes = Column(Text, nullable=True)  # JSON array of hashed codes
    totp_enabled_at = Column(DateTime, nullable=True)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_dept_active", "department", "is_active"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), default="New Chat")
    department = Column(String(50), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    document_context = Column(Text, nullable=True)
    document_name = Column(String(255), nullable=True)
    session_summary = Column(Text, nullable=True)
    summary_msg_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

    __table_args__ = (
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


class UserConnector(Base):
    __tablename__ = "user_connectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connector_id = Column(String(50), nullable=False)
    enabled = Column(Integer, default=1)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_user_connectors_user", "user_id", "connector_id", unique=True),
    )


class PendingAction(Base):
    """A destructive tool call awaiting user confirmation via the UI permission card.

    Created when the agent attempts to invoke a tool listed in
    agents.destructive_tools.DESTRUCTIVE_SLUGS. The SSE stream halts and
    emits a confirmation_required event carrying this row's id; the user
    clicks Allow or Deny in the chat UI which posts to
    /api/chat/confirm/{action_id} and updates status.
    """
    __tablename__ = "pending_actions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_slug = Column(String(100), nullable=False)
    tool_args = Column(Text, nullable=False)  # JSON-serialized arguments dict
    human_description = Column(Text, nullable=False)
    composio_session_id = Column(String(100), nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending|approved|denied|expired
    result = Column(Text, nullable=True)  # JSON-serialized tool execution result after approval
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # 1h TTL — see chat router

    __table_args__ = (
        Index("ix_pending_actions_user_status", "user_id", "status"),
        Index("ix_pending_actions_expires", "expires_at"),
    )


class TokenBlacklist(Base):
    """Revoked JWT tokens — checked on every authenticated request."""
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(36), unique=True, nullable=False)  # JWT ID
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    revoked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # Auto-cleanup after JWT expiry

    __table_args__ = (
        Index("ix_token_blacklist_jti", "jti", unique=True),
        Index("ix_token_blacklist_expires", "expires_at"),
    )
