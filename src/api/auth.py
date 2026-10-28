"""Password login, open self-registration of ordinary accounts and revocable browser sessions."""

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from src.api.deps import CurrentUser, DbSession
from src.config import settings
from src.db.auth import User, UserSession
from src.services.auth import (
    SESSION_SECONDS,
    UserContext,
    check_password,
    clear_successful_attempt,
    consume_login_attempt,
    consume_registration_attempt,
    create_session,
    hash_password,
    hasher,
    normalize_username,
    session_payload,
)
from src.services.auth_tokens import token_digest

router = APIRouter()


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr


class RegisterInput(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr


def _require_app_header(request: Request) -> str:
    # A custom header cannot be set by a cross-site form, so these unauthenticated POSTs
    # cannot be forged from another site.
    if request.headers.get("X-Requested-With") != "JudgeAI":
        raise HTTPException(403, "Запрос отклонён: нет заголовка приложения")
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "judgeai_session",
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post("/register", status_code=201)
async def register(payload: RegisterInput, request: Request, response: Response, db: DbSession):
    """Anyone may create an ordinary account; administrators are created only by the CLI."""
    client_host = _require_app_header(request)
    if not await consume_registration_attempt(db, client_host):
        raise HTTPException(
            429, "Слишком много регистраций с этого адреса; попробуйте через 15 минут"
        )
    try:
        username = normalize_username(payload.username)
        password_hash = await hash_password(payload.password.get_secret_value())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if await db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(409, "Это имя пользователя уже занято")
    user = User(username=username, password_hash=password_hash, is_admin=False)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:  # a concurrent registration took the name
        await db.rollback()
        raise HTTPException(409, "Это имя пользователя уже занято") from None
    token = await create_session(db, user)
    _set_session_cookie(response, token)
    return session_payload(UserContext(user.id, user.username, user.is_admin), token)


@router.post("/login")
async def login(payload: LoginInput, request: Request, response: Response, db: DbSession):
    client_host = _require_app_header(request)
    if not await consume_login_attempt(db, client_host, payload.username):
        raise HTTPException(429, "Слишком много попыток входа; попробуйте через 15 минут")
    user = await db.scalar(
        select(User).where(User.username == payload.username.strip().lower()).with_for_update()
    )
    password = payload.password.get_secret_value()
    valid = await check_password(user.password_hash if user else None, password)
    if not valid or user is None or not user.is_active:
        raise HTTPException(401, "Неверное имя пользователя или пароль")
    await clear_successful_attempt(db, client_host, user.username)
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hasher.hash, password)
    # Rotating a browser's authenticated session prevents session fixation.
    old_token = request.cookies.get("judgeai_session")
    if old_token:
        await db.execute(
            delete(UserSession).where(UserSession.token_hash == token_digest(old_token))
        )
    token = await create_session(db, user)
    _set_session_cookie(response, token)
    return session_payload(UserContext(user.id, user.username, user.is_admin), token)


@router.get("/me")
async def me(request: Request, response: Response, user: CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    return session_payload(user, request.cookies["judgeai_session"])


@router.post("/logout")
async def logout(request: Request, response: Response, db: DbSession, user: CurrentUser):
    await db.execute(
        delete(UserSession).where(
            UserSession.token_hash == token_digest(request.cookies["judgeai_session"])
        )
    )
    await db.commit()
    response.delete_cookie(
        "judgeai_session",
        path="/",
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
