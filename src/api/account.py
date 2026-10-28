"""Authenticated account actions; business orchestration lives behind repository ports."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.api.deps import CurrentUser, DbSession
from src.application.account import AccountError, AccountUseCases, AnalysisInProgress
from src.infrastructure.account_repository import SqlAccountRepository
from src.schemas.account import DeleteCases, PasswordChange, Profile
from src.services.auth import check_password, consume_login_attempt, hash_password

router = APIRouter()


def use_cases(db):
    return AccountUseCases(SqlAccountRepository(db), check_password, hash_password)


async def require_password_budget(db, user, request):
    host = request.client.host if request.client else "unknown"
    if not await consume_login_attempt(db, host, user.username):
        raise HTTPException(429, "Слишком много попыток; попробуйте через 15 минут")


@router.get("/profile", response_model=Profile)
async def profile(db: DbSession, user: CurrentUser):
    return await use_cases(db).profile(user.user_id)


@router.put("/profile", response_model=Profile)
async def save_profile(payload: Profile, db: DbSession, user: CurrentUser):
    return await use_cases(db).save_profile(user.user_id, payload.model_dump())


@router.post("/password")
async def password(payload: PasswordChange, request: Request, db: DbSession, user: CurrentUser):
    await require_password_budget(db, user, request)
    try:
        await use_cases(db).change_password(
            user.user_id,
            payload.current_password.get_secret_value(),
            payload.new_password.get_secret_value(),
            request.cookies["judgeai_session"],
        )
    except (AccountError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from None
    return {"ok": True}


@router.get("/sessions")
async def sessions(request: Request, db: DbSession, user: CurrentUser):
    return await use_cases(db).sessions(user.user_id, request.cookies["judgeai_session"])


@router.delete("/sessions/{session_id}")
async def revoke(session_id: str, request: Request, db: DbSession, user: CurrentUser):
    if not await use_cases(db).revoke(user.user_id, request.cookies["judgeai_session"], session_id):
        raise HTTPException(404, "Сеанс не найден; для текущего сеанса используйте выход")
    return {"ok": True}


@router.get("/export")
async def export(db: DbSession, user: CurrentUser):
    return JSONResponse(
        jsonable_encoder(await use_cases(db).export_data(user.user_id)),
        headers={
            "Content-Disposition": 'attachment; filename="judgeai-data.json"',
        },
    )


@router.post("/delete-cases")
async def remove_cases(payload: DeleteCases, request: Request, db: DbSession, user: CurrentUser):
    await require_password_budget(db, user, request)
    try:
        return await use_cases(db).delete_cases(
            user.user_id, payload.password.get_secret_value(), payload.confirmation
        )
    except AccountError as exc:
        raise HTTPException(400, str(exc)) from None
    except AnalysisInProgress:
        raise HTTPException(409, "Дождитесь завершения анализа перед удалением дел") from None
