"""Production-grade auth service with SQLAlchemy and argon2 hashing."""

import re
import uuid
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from db.models import User, TokenBlacklist

logger = logging.getLogger("triton.auth")


# --- Password hashing (argon2-like using pbkdf2_sha256 - stdlib, no extra dep) ---

PBKDF2_ITERATIONS = 600_000

# Password policy
MIN_PASSWORD_LENGTH = 8
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,128}$"
)


def validate_password_strength(password: str) -> None:
    """Enforce server-side password policy. Raises ValueError on failure."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > 128:
        raise ValueError("Password must be at most 128 characters")
    if not PASSWORD_PATTERN.match(password):
        raise ValueError(
            "Password must include at least one uppercase letter, "
            "one lowercase letter, and one number"
        )


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-SHA256 with random salt (OWASP-recommended iterations)."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored PBKDF2-SHA256 hash.

    Supports both legacy (100k iterations) and current (600k iterations) hashes.
    """
    try:
        salt_hex, key_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        stored_key = bytes.fromhex(key_hex)
        # Try current iteration count first
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
        if hmac.compare_digest(new_key, stored_key):
            return True
        # Fall back to legacy iteration count for existing hashes
        legacy_key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(legacy_key, stored_key)
    except (ValueError, AttributeError):
        return False


# --- User CRUD ---

def create_user(db: Session, email: str, password: str, name: str, department: str) -> User:
    # Enforce password policy server-side
    validate_password_strength(password)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("User with this email already exists")

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password(password),
        name=name,
        department=department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"User registered: {email} (dept={department})")
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email, User.is_active == 1).first()
    if not user:
        # Constant-time dummy hash to prevent timing-based user enumeration
        hash_password("dummy_password_to_prevent_timing_attack")
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id, User.is_active == 1).first()


def list_users(db: Session, department: Optional[str] = None) -> list[User]:
    query = db.query(User).filter(User.is_active == 1)
    if department:
        query = query.filter(User.department == department)
    return query.order_by(User.created_at.desc()).all()


def deactivate_user(db: Session, user_id: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    user.is_active = 0
    db.commit()
    logger.info(f"User deactivated: {user.email}")
    return True


# --- JWT ---

def create_access_token(user: User) -> str:
    jti = str(uuid.uuid4())  # Unique token ID for revocation
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": user.id,
        "email": user.email,
        "department": user.department,
        "name": user.name,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": jti,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


# --- 2FA challenge token (issued by /login when TOTP enabled, consumed by /login/2fa) ---

CHALLENGE_TOKEN_TTL_SECONDS = 300  # 5 minutes


def create_2fa_challenge_token(user_id: str) -> str:
    """Short-lived token proving the user passed the password step.
    Has no API access on its own — only valid at /login/2fa."""
    expire = datetime.utcnow() + timedelta(seconds=CHALLENGE_TOKEN_TTL_SECONDS)
    payload = {
        "sub": user_id,
        "purpose": "2fa_challenge",
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_2fa_challenge_token(token: str) -> Optional[str]:
    """Return user_id if the challenge token is valid, else None."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("purpose") != "2fa_challenge":
        return None
    return payload.get("sub")


# --- Token blacklist ---

def blacklist_token(db: Session, jti: str, user_id: str, expires_at: datetime) -> None:
    """Add a token to the blacklist (for logout)."""
    entry = TokenBlacklist(jti=jti, user_id=user_id, expires_at=expires_at)
    db.add(entry)
    db.commit()


def is_token_blacklisted(db: Session, jti: str) -> bool:
    """Check if a token has been revoked."""
    return db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first() is not None


def cleanup_expired_blacklist(db: Session) -> int:
    """Remove expired entries from blacklist (housekeeping)."""
    result = db.query(TokenBlacklist).filter(
        TokenBlacklist.expires_at < datetime.utcnow()
    ).delete()
    db.commit()
    return result
