from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class Department(str, Enum):
    ADMIN = "admin"
    SALES = "sales"
    OPERATIONS = "operations"
    FINANCE = "finance"
    EXECUTIVE = "executive"


# --- Auth ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    department: Department

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        return v.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    department: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserResponse] = None
    requires_2fa: bool = False
    challenge_token: Optional[str] = None


# --- 2FA ---

class TwoFactorLoginRequest(BaseModel):
    challenge_token: str = Field(..., min_length=10, max_length=2048)
    code: str = Field(..., min_length=6, max_length=20)  # 6-digit TOTP or backup code


class TwoFactorSetupResponse(BaseModel):
    secret: str  # base32 — show in case QR can't be scanned
    qr_code_png_b64: str
    backup_codes: List[str]


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)  # TOTP only at setup


class TwoFactorDisableRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=6, max_length=20)


class TwoFactorRegenerateRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
    code: str = Field(..., min_length=6, max_length=20)


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    enabled_at: Optional[str] = None
    backup_codes_remaining: int = 0


# --- Chat ---

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10_000)
    session_id: Optional[str] = Field(None, max_length=36)
    document_context: Optional[str] = Field(None, max_length=50_000)
    document_name: Optional[str] = Field(None, max_length=255)


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""


# --- Sessions ---

class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


class SessionResponse(BaseModel):
    id: str
    title: str
    department: str
    user_id: str
    created_at: str
    updated_at: str
    message_count: int = 0


class SessionDetailResponse(SessionResponse):
    messages: List[ChatMessage] = []
