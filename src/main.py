import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api import (
    account,
    auth,
    chats,
    criminal_sanctions,
    document_previews,
    knowledge,
    legal_library,
    precedents,
)
from src.config import settings
from src.db.session import async_session_factory
from src.services.analysis_runner import fail_interrupted_analyses

logger = logging.getLogger(__name__)


def configure_logging(level: str | None = None) -> None:
    """Emit our own loggers at LOG_LEVEL (default INFO) to stdout.

    Without this, the root logger has no handler under uvicorn and every ``logger.info``
    (analysis stage timings, window cache hits, LLM latency) is silently dropped — only
    warnings/errors reach ``docker logs``. When the root logger already has handlers
    (pytest, a custom deployment) records simply propagate there and none is added.
    """
    app_level = (level or settings.LOG_LEVEL).upper()
    app_logger = logging.getLogger("src")
    app_logger.setLevel(app_level)
    if not app_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app_logger.addHandler(handler)
        app_logger.propagate = False


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    interrupted = await fail_interrupted_analyses()
    if interrupted:
        logger.warning("marked %s interrupted analyses as failed", interrupted)
    yield


app = FastAPI(
    title="JudgeAI",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_previews.router, prefix="/api", tags=["document previews"])
app.include_router(account.router, prefix="/api/account", tags=["account"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(precedents.router, prefix="/api/chats", tags=["precedents"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(legal_library.router, prefix="/api/legal", tags=["legal library"])
app.include_router(
    criminal_sanctions.router, prefix="/api/legal/sanctions", tags=["criminal sanctions"]
)


@app.exception_handler(RequestValidationError)
async def hide_auth_validation_inputs(request, exc):
    if request.url.path.startswith(("/api/auth", "/api/account", "/api/document-previews")):
        # A missing field can otherwise echo the entire login body, including passwords.
        errors = [{key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def private_response_cache_control(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(
        ("/api/chats", "/api/knowledge", "/api/auth", "/api/account", "/api/document-previews")
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health_check():
    """Liveness probe polled by the deploy job after `docker compose up`.

    A reachable API with a dead database (recovery mode, out of disk) is not a
    healthy service: the deploy poll must see 503 instead of a blind 200.
    """
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("health check: database unavailable")
        return JSONResponse(
            status_code=503, content={"status": "degraded", "database": "unavailable"}
        )
    return {"status": "ok", "database": "ok"}
