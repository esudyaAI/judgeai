"""Authentication primitives; no secrets, passwords or document text in errors/logs."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.db.auth import LoginBucket, User, UserSession
from src.services.auth_tokens import (
    csrf_for,
    login_bucket_keys,
    new_session_token,
    registration_bucket_key,
    token_digest,
)

hasher = PasswordHasher()
# Match the missing-account password verification cost without a usable default account.
DUMMY_HASH = hasher.hash(new_session_token())
SESSION_SECONDS = 8 * 60 * 60
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,79}")
# Open registration on a public site: a host may create this many accounts per window.
REGISTRATIONS_PER_HOST = 10
_BUCKET_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True)
class UserContext:
    user_id: int
    username: str
    is_admin: bool = False


async def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Пароль должен содержать от 12 до 1024 символов")
    return await run_in_threadpool(hasher.hash, password)


async def check_password(encoded: str | None, password: str) -> bool:
    if not 1 <= len(password) <= 1024:
        return False
    try:
        await run_in_threadpool(hasher.verify, encoded or DUMMY_HASH, password)
        return encoded is not None
    except (VerificationError, InvalidHashError):
        return False


async def _consume_bucket(db: AsyncSession, key: str, limit: int, now: datetime) -> bool:
    """Count one attempt against a key; False once the window's limit is exceeded."""
    reset = now + _BUCKET_WINDOW
    statement = insert(LoginBucket).values(key=key, attempts=1, resets_at=reset)
    statement = statement.on_conflict_do_update(
        index_elements=[LoginBucket.key],
        set_={
            "attempts": case((LoginBucket.resets_at <= now, 1), else_=LoginBucket.attempts + 1),
            "resets_at": case((LoginBucket.resets_at <= now, reset), else_=LoginBucket.resets_at),
        },
    ).returning(LoginBucket.attempts)
    return await db.scalar(statement) <= limit


async def consume_login_attempt(db: AsyncSession, client_host: str, username: str) -> bool:
    now = datetime.now(UTC)
    await db.execute(delete(LoginBucket).where(LoginBucket.resets_at <= now))
    account_key, host_key = login_bucket_keys(client_host, username)
    # The host budget protects bulk requests; per-account failures are independent
    # even when multiple users reach the API through the same development proxy.
    for key, limit in ((host_key, 100), (account_key, 10)):
        if not await _consume_bucket(db, key, limit, now):
            await db.commit()
            return False
    await db.commit()
    return True


async def consume_registration_attempt(db: AsyncSession, client_host: str) -> bool:
    now = datetime.now(UTC)
    allowed = await _consume_bucket(
        db, registration_bucket_key(client_host), REGISTRATIONS_PER_HOST, now
    )
    await db.commit()
    return allowed


def normalize_username(username: str) -> str:
    """Lowercased login; ValueError when it breaks the account naming rule."""
    name = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(name):
        raise ValueError(
            "Имя пользователя: от 3 до 80 символов — латинские буквы, цифры, точка, "
            "дефис или подчёркивание; начинается с буквы или цифры"
        )
    return name


async def clear_successful_attempt(db: AsyncSession, client_host: str, username: str) -> None:
    account_key, host_key = login_bucket_keys(client_host, username)
    await db.execute(
        update(LoginBucket)
        .where(LoginBucket.key == host_key)
        .values(attempts=case((LoginBucket.attempts > 0, LoginBucket.attempts - 1), else_=0))
    )
    await db.execute(delete(LoginBucket).where(LoginBucket.key == account_key))


async def create_session(db: AsyncSession, user: User) -> str:
    now = datetime.now(UTC)
    await db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    token = new_session_token()
    db.add(
        UserSession(
            token_hash=token_digest(token),
            user_id=user.id,
            expires_at=now + timedelta(seconds=SESSION_SECONDS),
        )
    )
    await db.commit()
    return token


async def resolve_session(db: AsyncSession, token: str) -> UserContext | None:
    if not 40 <= len(token) <= 128:
        return None
    user = await db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_digest(token),
            UserSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    )
    return UserContext(user.id, user.username, user.is_admin) if user else None


def session_payload(user: UserContext, token: str) -> dict:
    return {
        "id": user.user_id,
        "username": user.username,
        "is_admin": user.is_admin,
        "csrf_token": csrf_for(token),
    }
