import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.services.auth import UserContext, resolve_session
from src.services.auth_tokens import csrf_for

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def require_user(request: Request, db: DbSession) -> UserContext:
    token = request.cookies.get("judgeai_session", "")
    user = await resolve_session(db, token)
    if user is None:
        raise HTTPException(401, "Требуется вход")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(supplied, csrf_for(token)):
            raise HTTPException(403, "Недействительный CSRF-токен; обновите страницу")
    return user


CurrentUser = Annotated[UserContext, Depends(require_user)]


async def require_admin(user: CurrentUser) -> UserContext:
    if not user.is_admin:
        raise HTTPException(403, "Требуются права администратора")
    return user


AdminUser = Annotated[UserContext, Depends(require_admin)]
