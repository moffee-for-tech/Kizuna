"""SQLAlchemy database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

# SQLite doesn't support pool_size/max_overflow — only use those for PostgreSQL
connect_args = {}
engine_kwargs = {"echo": False}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_kwargs["connect_args"] = connect_args
else:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (for dev — use Alembic in prod)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import text
        # Acquire an advisory lock so concurrent workers don't run create_all / migrations at the same time
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(1913586226)"))
            Base.metadata.create_all(bind=conn)
            _migrate_user_connectors(bind=conn)
            _migrate_session_document(bind=conn)
            _migrate_session_summary(bind=conn)
            _migrate_user_totp(bind=conn)
    else:
        Base.metadata.create_all(bind=engine)
        _migrate_user_connectors()
        _migrate_session_document()
        _migrate_session_summary()
        _migrate_user_totp()


_is_postgres = not settings.DATABASE_URL.startswith("sqlite")

# Use TIMESTAMP for PostgreSQL, DATETIME for SQLite
_TS_TYPE = "TIMESTAMP" if _is_postgres else "DATETIME"
_INT_DEFAULT = "INTEGER DEFAULT 0"

_ALLOWED_CONNECTOR_COLS = {
    "access_token": "TEXT",
    "refresh_token": "TEXT",
    "token_expires_at": _TS_TYPE,
}

_ALLOWED_SESSION_COLS = {
    "document_context": "TEXT",
    "document_name": "VARCHAR(255)",
    "session_summary": "TEXT",
    "summary_msg_count": _INT_DEFAULT,
}

_ALLOWED_USER_COLS = {
    "totp_secret_encrypted": "TEXT",
    "totp_enabled": _INT_DEFAULT,
    "totp_backup_codes": "TEXT",
    "totp_enabled_at": _TS_TYPE,
}


def _safe_add_columns(conn, table: str, new_cols: dict, allowed: dict, existing: set):
    """Add columns only if they are in the allow-list."""
    from sqlalchemy import text
    for col, col_type in new_cols.items():
        if col not in existing and col in allowed and allowed[col] == col_type:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


def _migrate_user_connectors(bind=None):
    """Add OAuth token columns to user_connectors if they don't exist (dev migration)."""
    from sqlalchemy import text, inspect as sa_inspect
    target = bind if bind is not None else engine
    insp = sa_inspect(target)
    if "user_connectors" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("user_connectors")}
    new_cols = {
        "access_token": "TEXT",
        "refresh_token": "TEXT",
        "token_expires_at": "DATETIME",
    }
    if bind is not None:
        _safe_add_columns(bind, "user_connectors", new_cols, _ALLOWED_CONNECTOR_COLS, existing_cols)
    else:
        with engine.begin() as conn:
            _safe_add_columns(conn, "user_connectors", new_cols, _ALLOWED_CONNECTOR_COLS, existing_cols)


def _migrate_session_document(bind=None):
    """Add document_context/document_name columns to chat_sessions if they don't exist."""
    from sqlalchemy import text, inspect as sa_inspect
    target = bind if bind is not None else engine
    insp = sa_inspect(target)
    if "chat_sessions" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("chat_sessions")}
    new_cols = {
        "document_context": "TEXT",
        "document_name": "VARCHAR(255)",
    }
    if bind is not None:
        _safe_add_columns(bind, "chat_sessions", new_cols, _ALLOWED_SESSION_COLS, existing_cols)
    else:
        with engine.begin() as conn:
            _safe_add_columns(conn, "chat_sessions", new_cols, _ALLOWED_SESSION_COLS, existing_cols)


def _migrate_session_summary(bind=None):
    """Add session_summary and summary_msg_count columns if missing."""
    from sqlalchemy import inspect as sa_inspect, text
    target = bind if bind is not None else engine
    inspector = sa_inspect(target)
    if "chat_sessions" not in inspector.get_table_names():
        return
    existing_cols = {col["name"] for col in inspector.get_columns("chat_sessions")}
    new_cols = {
        "session_summary": "TEXT",
        "summary_msg_count": "INTEGER DEFAULT 0",
    }
    if bind is not None:
        _safe_add_columns(bind, "chat_sessions", new_cols, _ALLOWED_SESSION_COLS, existing_cols)
    else:
        with engine.begin() as conn:
            _safe_add_columns(conn, "chat_sessions", new_cols, _ALLOWED_SESSION_COLS, existing_cols)


def _migrate_user_totp(bind=None):
    """Add TOTP 2FA columns to users table if missing."""
    from sqlalchemy import inspect as sa_inspect
    target = bind if bind is not None else engine
    insp = sa_inspect(target)
    if "users" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("users")}
    new_cols = {
        "totp_secret_encrypted": "TEXT",
        "totp_enabled": _INT_DEFAULT,
        "totp_backup_codes": "TEXT",
        "totp_enabled_at": _TS_TYPE,
    }
    if bind is not None:
        _safe_add_columns(bind, "users", new_cols, _ALLOWED_USER_COLS, existing_cols)
    else:
        with engine.begin() as conn:
            _safe_add_columns(conn, "users", new_cols, _ALLOWED_USER_COLS, existing_cols)

