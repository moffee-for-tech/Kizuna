"""Kizuna AI Chat Platform — Production-grade FastAPI application."""

import logging
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from routers import auth, chat, sessions, upload, connectors
from db.database import init_db, SessionLocal
from config import settings

# --- Structured logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("kizuna")

# --- Rate limiter ---
limiter = Limiter(key_func=get_remote_address)

is_production = settings.ENVIRONMENT == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Kizuna AI Chat Platform starting...")

    # Initialize database tables
    init_db()
    logger.info("Database initialized")

    yield
    logger.info("Kizuna shutting down...")


app = FastAPI(
    title="Kizuna AI Chat Platform",
    description="Five-role AI chat platform with Gemini LLM via OpenRouter, multi-agent system, and Composio tools",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if is_production else "/api/docs",
    redoc_url=None if is_production else "/api/redoc",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — validate origins
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if "*" in origins:
    if is_production:
        raise SystemExit("FATAL: CORS wildcard origin not allowed in production")
    logger.warning("CORS wildcard origin detected — disabling allow_credentials for safety")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- Security headers middleware ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Core security headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # HSTS — enforce HTTPS (only in production)
    if is_production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

    # Content-Security-Policy
    csp_origins = " ".join(origins) if origins else "'self'"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        f"connect-src 'self' {csp_origins}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # Prevent caching of authenticated responses
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"

    return response

# Mount routers
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(connectors.router)


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    incident_id = uuid.uuid4().hex[:12]
    logger.error(f"Unhandled error (incident={incident_id}): {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# --- Health checks ---
@app.get("/api/health")
async def health_check():
    """Basic health check — no sensitive info exposed."""
    return {"status": "healthy"}


@app.get("/api/health/deep")
async def deep_health_check():
    """Deep health check — tests DB connectivity."""
    checks = {"database": "unknown"}

    try:
        from sqlalchemy import text
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        checks["database"] = "unhealthy"

    overall = all(v == "healthy" for v in checks.values())
    return {"status": "healthy" if overall else "degraded"}
