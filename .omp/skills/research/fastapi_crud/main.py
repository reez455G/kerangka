# =============================================================================
# main.py — FastAPI Application Factory
#
# Tanggung jawab file ini:
#   1. Buat instance FastAPI dengan metadata (title, version, docs URL)
#   2. Pasang middleware: CORS, structured logging, request ID
#   3. Konfigurasi rate limiting dengan SlowAPI
#   4. Include semua router (/auth, /users, /posts)
#   5. Register global exception handlers (HTTPException, ValidationError)
#   6. Startup/shutdown events (buat tabel, tutup DB pool)
#
# Jalankan:
#   uvicorn main:app --reload --port 8000
#   atau: python main.py
# =============================================================================

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from config import get_settings
from database import create_tables
from routers import auth, posts, users

settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# 1. Logging — Structured JSON-like format
# ─────────────────────────────────────────────────────────────────────────────
def setup_logging() -> None:
    """
    Konfigurasi logging ke stdout dengan format yang mudah di-parse.
    Di production, ganti dengan library seperti structlog atau loguru
    untuk output JSON yang bisa di-ingest oleh ELK/Datadog.
    """
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    logging.basicConfig(
        stream=sys.stdout,
        level=log_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Kurangi noise dari library
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.DEBUG else logging.WARNING
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Rate Limiter (SlowAPI — Starlette wrapper untuk limits)
# ─────────────────────────────────────────────────────────────────────────────
# get_remote_address mengambil IP dari X-Forwarded-For atau client.host
# Di belakang reverse proxy, pastikan trusted proxy di-set dengan benar
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],   # "60/minute"
)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Lifespan (startup + shutdown)
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI modern lifecycle hook (gantikan @app.on_event yang deprecated).

    STARTUP:
      - Buat tabel database (development / testing)
      - Di production, gunakan Alembic migration, BUKAN create_tables()

    SHUTDOWN:
      - FastAPI + SQLAlchemy menutup pool secara otomatis
      - Tambahkan cleanup lain di sini (menutup Redis, dll.)
    """
    logger.info("🚀 Aplikasi starting — %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await create_tables()   # Buat tabel jika belum ada (idempotent)
    logger.info("✅ Database tables siap")
    yield
    logger.info("🛑 Aplikasi shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Buat aplikasi FastAPI
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## REST API dengan FastAPI + SQLAlchemy + PostgreSQL

### Fitur
- **JWT Authentication** (access token 30m + refresh token 7d)
- **Role-based Authorization** (Admin / Editor / Viewer)
- **Pagination** untuk semua endpoint list (`?page=1&page_size=20`)
- **Filtering** via query parameters
- **Rate Limiting** (60 req/menit per IP, 10/menit di /auth/login)
- **Soft Delete** (data tidak benar-benar dihapus)

### Cara mulai
1. `POST /auth/login` → dapat `access_token`
2. Set header: `Authorization: Bearer <access_token>`
3. Akses endpoint yang dilindungi
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Middleware
# ─────────────────────────────────────────────────────────────────────────────

# ── CORS ──────────────────────────────────────────────────────────────────────
# Di production, ganti allow_origins dengan domain spesifik
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# ── Request ID + Timing Middleware ────────────────────────────────────────────
@app.middleware("http")
async def request_context_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware yang:
    1. Buat request_id unik per request (untuk tracing log lintas service)
    2. Ukur waktu pemrosesan
    3. Tambahkan header X-Request-ID dan X-Process-Time ke response

    Format log:
      2024-01-15T10:30:00 | INFO | main | GET /posts 200 [12.3ms] req=abc-123
    """
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Unhandled exception: %s | req=%s | path=%s",
            exc, request_id, request.url.path,
            exc_info=True,
        )
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s %d [%.1fms] req=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
    return response


# ─────────────────────────────────────────────────────────────────────────────
# 6. Exception Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Format konsisten untuk error rate limit."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Terlalu banyak request. Coba lagi dalam 1 menit.",
            "code": "RATE_LIMIT_EXCEEDED",
        },
        headers={"Retry-After": "60"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Pydantic validation error → format yang lebih ramah klien.
    Default FastAPI mengembalikan struktur bersarang yang sulit di-parse.
    """
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({
            "field": field or "body",
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validasi gagal", "errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Format error konsisten untuk semua HTTPException."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all untuk exception yang tidak terduga."""
    logger.error("Unexpected error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Terjadi kesalahan internal server",
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Include Routers
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Health Check
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"], summary="Health check")
async def health_check():
    """
    Digunakan oleh load balancer / Kubernetes liveness probe.
    Bisa diperluas untuk cek koneksi DB, Redis, dll.
    """
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}", "docs": "/docs"}


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
