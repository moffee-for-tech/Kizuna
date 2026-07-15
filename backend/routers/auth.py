"""Auth router — login, register, logout, user management, 2FA."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from models import (
    UserCreate,
    UserLogin,
    TokenResponse,
    UserResponse,
    TwoFactorLoginRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    TwoFactorDisableRequest,
    TwoFactorRegenerateRequest,
    TwoFactorStatusResponse,
)
from services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token,
    decode_access_token,
    blacklist_token,
    list_users,
    deactivate_user,
    verify_password,
    create_2fa_challenge_token,
    decode_2fa_challenge_token,
)
from services import totp_service
from db.models import User
from middleware.rbac import get_current_user
from db.database import get_db
from config import settings

logger = logging.getLogger("kizuna.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


def _set_auth_cookie(response: Response, token: str) -> None:
    """Set httpOnly secure cookie with JWT."""
    response.set_cookie(
        key="kizuna_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    """Clear the auth cookie."""
    response.delete_cookie(
        key="kizuna_token",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        department=user.department,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, data: UserLogin, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Login attempt: {data.email} from {client_ip}")

    user = authenticate_user(db, data.email, data.password)
    if not user:
        logger.warning(f"Failed login: {data.email} from {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # If 2FA is enabled, return a challenge token instead of a session JWT.
    if user.totp_enabled and user.totp_secret_encrypted:
        challenge = create_2fa_challenge_token(user.id)
        logger.info(f"2FA challenge issued: {data.email} from {client_ip}")
        return TokenResponse(requires_2fa=True, challenge_token=challenge)

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    logger.info(f"Successful login: {data.email} from {client_ip}")

    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/login/2fa", response_model=TokenResponse)
@limiter.limit("5/15minute")
async def login_2fa(
    request: Request,
    response: Response,
    data: TwoFactorLoginRequest,
    db: Session = Depends(get_db),
):
    """Step 2 of login when 2FA is enabled. Accepts a TOTP code or a backup code."""
    client_ip = request.client.host if request.client else "unknown"

    user_id = decode_2fa_challenge_token(data.challenge_token)
    if not user_id:
        logger.warning(f"Invalid 2FA challenge token from {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid or expired challenge")

    user = db.query(User).filter(User.id == user_id, User.is_active == 1).first()
    if not user or not user.totp_enabled or not user.totp_secret_encrypted:
        raise HTTPException(status_code=401, detail="2FA not enabled for this account")

    secret = totp_service.decrypt_secret(user.totp_secret_encrypted)
    if not secret:
        raise HTTPException(status_code=500, detail="2FA secret unreadable — contact admin")

    code = data.code.strip().replace(" ", "")
    accepted = False

    # Try TOTP first (6 digits), then fall back to backup code.
    if code.isdigit() and len(code) == 6:
        accepted = totp_service.verify_code(secret, code)
    if not accepted:
        new_codes_json = totp_service.verify_and_consume_backup_code(
            user.totp_backup_codes, code
        )
        if new_codes_json is not None:
            user.totp_backup_codes = new_codes_json
            db.commit()
            accepted = True
            logger.info(f"2FA backup code consumed by {user.email} from {client_ip}")

    if not accepted:
        logger.warning(f"Failed 2FA verification: {user.email} from {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    token = create_access_token(user)
    _set_auth_cookie(response, token)
    logger.info(f"Successful 2FA login: {user.email} from {client_ip}")
    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/hour")
async def register(request: Request, response: Response, data: UserCreate, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Registration attempt: {data.email} from {client_ip}")

    try:
        user = create_user(
            db=db,
            email=data.email,
            password=data.password,
            name=data.name,
            department=data.department.value,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token(user)
    _set_auth_cookie(response, token)

    return TokenResponse(access_token=token, user=_user_response(user))


@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke current token and clear auth cookie."""
    jti = current_user.get("jti")
    if jti:
        # Blacklist the token so it can't be reused
        blacklist_token(db, jti, current_user["id"], datetime.utcnow())

    _clear_auth_cookie(response)
    logger.info(f"Logout: {current_user['email']}")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        name=current_user["name"],
        department=current_user["department"],
        created_at="",
    )


# --- Admin-only user management ---

@router.get("/users")
async def get_all_users(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users (admin only)."""
    if current_user["department"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    users = list_users(db)
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            name=u.name,
            department=u.department,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a user (admin only, soft delete)."""
    if current_user["department"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if current_user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    if not deactivate_user(db, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    logger.info(f"Admin {current_user['email']} deactivated user {user_id}")
    return {"detail": "User deactivated"}


# --- 2FA management ---

def _backup_codes_remaining(stored_json: str | None) -> int:
    if not stored_json:
        return 0
    try:
        return len(json.loads(stored_json))
    except (ValueError, TypeError):
        return 0


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/2fa/status", response_model=TwoFactorStatusResponse)
async def two_factor_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _get_user_or_404(db, current_user["id"])
    return TwoFactorStatusResponse(
        enabled=bool(user.totp_enabled),
        enabled_at=user.totp_enabled_at.isoformat() if user.totp_enabled_at else None,
        backup_codes_remaining=_backup_codes_remaining(user.totp_backup_codes),
    )


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
@limiter.limit("5/hour")
async def two_factor_setup(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a new TOTP secret + QR + backup codes.
    The secret is stored encrypted but `totp_enabled` stays false until /verify succeeds —
    so a typo during enrollment can't lock the user out."""
    user = _get_user_or_404(db, current_user["id"])
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled — disable it first")

    secret = totp_service.generate_secret()
    plain_codes, hashed_json = totp_service.generate_backup_codes()

    user.totp_secret_encrypted = totp_service.encrypt_secret(secret)
    user.totp_backup_codes = hashed_json
    user.totp_enabled = 0
    user.totp_enabled_at = None
    db.commit()

    qr_b64 = totp_service.generate_qr_png_b64(user.email, secret)
    logger.info(f"2FA setup initiated by {user.email}")
    return TwoFactorSetupResponse(
        secret=secret,
        qr_code_png_b64=qr_b64,
        backup_codes=plain_codes,
    )


@router.post("/2fa/verify")
@limiter.limit("10/15minute")
async def two_factor_verify(
    request: Request,
    data: TwoFactorVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm the user can produce a valid TOTP code, then activate 2FA."""
    user = _get_user_or_404(db, current_user["id"])
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    if not user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="Run /2fa/setup first")

    secret = totp_service.decrypt_secret(user.totp_secret_encrypted)
    if not secret or not totp_service.verify_code(secret, data.code.strip()):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    user.totp_enabled = 1
    user.totp_enabled_at = datetime.utcnow()
    db.commit()
    logger.info(f"2FA enabled for {user.email}")
    return {"detail": "2FA enabled"}


@router.post("/2fa/disable")
@limiter.limit("5/15minute")
async def two_factor_disable(
    request: Request,
    data: TwoFactorDisableRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requires both password and a current TOTP/backup code to disable."""
    user = _get_user_or_404(db, current_user["id"])
    if not user.totp_enabled or not user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    secret = totp_service.decrypt_secret(user.totp_secret_encrypted)
    code = data.code.strip().replace(" ", "")
    accepted = bool(secret) and totp_service.verify_code(secret, code)
    if not accepted:
        new_codes = totp_service.verify_and_consume_backup_code(user.totp_backup_codes, code)
        if new_codes is not None:
            user.totp_backup_codes = new_codes
            accepted = True
    if not accepted:
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    user.totp_enabled = 0
    user.totp_secret_encrypted = None
    user.totp_backup_codes = None
    user.totp_enabled_at = None
    db.commit()
    logger.info(f"2FA disabled by {user.email}")
    return {"detail": "2FA disabled"}


@router.post("/2fa/backup-codes/regenerate")
@limiter.limit("3/hour")
async def two_factor_regenerate_backup_codes(
    request: Request,
    data: TwoFactorRegenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a fresh set of 8 backup codes — invalidates all previous codes."""
    user = _get_user_or_404(db, current_user["id"])
    if not user.totp_enabled or not user.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    secret = totp_service.decrypt_secret(user.totp_secret_encrypted)
    if not secret or not totp_service.verify_code(secret, data.code.strip()):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    plain_codes, hashed_json = totp_service.generate_backup_codes()
    user.totp_backup_codes = hashed_json
    db.commit()
    logger.info(f"2FA backup codes regenerated by {user.email}")
    return {"backup_codes": plain_codes}


@router.post("/users/{user_id}/2fa/disable")
async def admin_force_disable_2fa(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin-only: force-disable 2FA for a user (lost-device recovery). Audit-logged."""
    if current_user["department"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if not target.totp_enabled and not target.totp_secret_encrypted:
        return {"detail": "2FA was not enabled"}
    target.totp_enabled = 0
    target.totp_secret_encrypted = None
    target.totp_backup_codes = None
    target.totp_enabled_at = None
    db.commit()
    logger.warning(
        f"Admin {current_user['email']} force-disabled 2FA for user {target.email} (id={user_id})"
    )
    return {"detail": "2FA force-disabled"}
