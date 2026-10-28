import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api import account, auth, chats, criminal_sanctions, knowledge, legal_library, precedents
from src.config import settings
from src.services.analysis_runner import fail_interrupted_analyses

logger = logging.getLogger(__name__)


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
    if request.url.path.startswith(("/api/auth", "/api/account")):
        # A missing field can otherwise echo the entire login body, including passwords.
        errors = [{key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def private_response_cache_control(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/chats", "/api/knowledge", "/api/auth", "/api/account")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
async def health_check():
    """Liveness probe polled by the deploy job after `docker compose up`."""
    return {"status": "ok"}
