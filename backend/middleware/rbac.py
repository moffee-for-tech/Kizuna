"""Production RBAC middleware with DB-backed user validation and token revocation."""

import logging

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from services.auth_service import decode_access_token, get_user_by_id, is_token_blacklisted
from db.database import get_db

logger = logging.getLogger("triton.auth")

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    """Extract and validate JWT from httpOnly cookie or Authorization header.
    Check token blacklist for revoked sessions."""

    token = None

    # Priority 1: httpOnly cookie
    cookie_token = request.cookies.get("triton_token")
    if cookie_token:
        token = cookie_token

    # Priority 2: Authorization header (for API clients / mobile)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check token blacklist (logout revocation)
    jti = payload.get("jti")
    if jti and is_token_blacklisted(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    user = get_user_by_id(db, payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "department": user.department,
        "jti": jti,
    }


def require_department(allowed_departments: list[str]):
    """Dependency that checks if the current user belongs to an allowed department."""

    async def check_department(current_user: dict = Depends(get_current_user)):
        if current_user["department"] not in allowed_departments:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied for your department",
            )
        return current_user

    return check_department
