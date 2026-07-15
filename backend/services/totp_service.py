"""TOTP (RFC 6238) service for optional 2FA.

Compatible with Google Authenticator, Microsoft Authenticator, Authy, 1Password.
Secrets are Fernet-encrypted at rest using a key derived from JWT_SECRET.
Backup codes are stored as PBKDF2-SHA256 hashes (single-use).
"""

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import secrets
from typing import Optional

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger("kizuna.totp")

ISSUER = "Kizuna AI"
BACKUP_CODE_COUNT = 8
BACKUP_CODE_BYTES = 5  # ~10 hex chars per code
BACKUP_HASH_ITERATIONS = 200_000


def _fernet() -> Fernet:
    """Derive a Fernet key from JWT_SECRET via SHA-256 (32 bytes → urlsafe-b64)."""
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET not configured — cannot encrypt TOTP secret")
    digest = hashlib.sha256(b"kizuna-totp-v1|" + settings.JWT_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def generate_secret() -> str:
    """Generate a fresh base32 TOTP secret (160 bits)."""
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> Optional[str]:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        logger.error("Failed to decrypt TOTP secret — JWT_SECRET may have rotated")
        return None


def provisioning_uri(email: str, secret: str) -> str:
    """otpauth:// URI for authenticator app enrollment."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def generate_qr_png_b64(email: str, secret: str) -> str:
    """Render the otpauth URI as a PNG QR code, return base64-encoded."""
    img = qrcode.make(provisioning_uri(email, secret))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code with ±1 step (30s) tolerance for clock drift."""
    if not code or not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# --- Backup codes ---

def _hash_backup_code(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, BACKUP_HASH_ITERATIONS)


def _format_code(raw: bytes) -> str:
    """8-char hyphenated hex like 'a1b2-c3d4'."""
    h = raw.hex()
    return f"{h[:4]}-{h[4:8]}"


def generate_backup_codes() -> tuple[list[str], str]:
    """Return (plaintext_codes_for_user, json_of_hashed_codes_for_db)."""
    plain: list[str] = []
    hashed: list[dict] = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_bytes(BACKUP_CODE_BYTES)
        code = _format_code(raw[:4])  # 8 hex chars hyphenated
        salt = os.urandom(16)
        h = _hash_backup_code(code, salt)
        plain.append(code)
        hashed.append({"s": salt.hex(), "h": h.hex()})
    return plain, json.dumps(hashed)


def verify_and_consume_backup_code(stored_json: Optional[str], code: str) -> Optional[str]:
    """If `code` matches one of the stored hashes, return updated JSON with it removed.
    Returns None if no match — caller should treat as failed verification."""
    if not stored_json or not code:
        return None
    code = code.strip().lower()
    try:
        entries = json.loads(stored_json)
    except (ValueError, TypeError):
        return None
    matched_idx = -1
    for i, entry in enumerate(entries):
        salt = bytes.fromhex(entry["s"])
        expected = bytes.fromhex(entry["h"])
        candidate = _hash_backup_code(code, salt)
        if hmac.compare_digest(candidate, expected):
            matched_idx = i
            break
    if matched_idx < 0:
        return None
    entries.pop(matched_idx)
    return json.dumps(entries)
