import logging
import time

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import CurrentUser, DbSession
from src.application.account import AnalysisInProgress
from src.application.chat_deletion import ChatNotFound, delete_chat
from src.application.chat_pinning import pin_chat
from src.db.models import Attachment, Chat, Message
from src.infrastructure.chat_deletion import SqlChatDeletionRepository
from src.infrastructure.chat_pinning import SqlChatPinRepository
from src.infrastructure.chat_queries import owned_chat_query
from src.schemas.chat import ChatCreate, ChatPin, ChatRead, ChatStatus
from src.schemas.message import MessageRead, MessageSendResponse
from src.services.analysis_runner import run_analysis
from src.services.file_reader import save_upload_file, validate_extension

logger = logging.getLogger(__name__)

router = APIRouter()


def _derive_chat_status(messages: list[tuple[str, bool]]) -> ChatStatus:
    """Dot state of one case from its assistant messages ordered by id.

    The newest exchange decides, but a completed answer without case content
    (a text-only follow-up like «Вопрос не содержит сведений…»: no defendants,
    no documents) never repaints the case: a failed analysis stays red until a
    real re-analysis with case content completes (T47).
    """
    for status, has_case in reversed(messages):
        if status in ("pending", "running"):
            return "busy"
        if status == "failed":
            return "failed"
        if status == "completed" and has_case:
            return "ready"
    if messages and messages[-1][0] == "completed":
        # A purely textual chat with a normal answer stays ready.
        return "ready"
    return "draft"


async def _chat_statuses(db: AsyncSession, chat_ids: list[int]) -> dict[int, ChatStatus]:
    if not chat_ids:
        return {}
    # Case content flags are computed in SQL so the big analysis JSONB is never
    # transferred just to derive a sidebar dot.
    documents = Message.analysis["stats"]["documents"]
    case_content = or_(
        func.jsonb_array_length(Message.analysis["defendants"]) > 0,
        func.coalesce(documents.astext, "0") != "0",
    )
    rows = (
        await db.execute(
            select(Message.chat_id, Message.status, case_content.label("case_content"))
            .where(Message.chat_id.in_(chat_ids), Message.role == "assistant")
            .order_by(Message.id)
        )
    ).all()
    by_chat: dict[int, list[tuple[str, bool]]] = {}
    for chat_id, status, has_case in rows:
        by_chat.setdefault(chat_id, []).append((status, bool(has_case)))
    return {chat_id: _derive_chat_status(messages) for chat_id, messages in by_chat.items()}


async def load_message(db: AsyncSession, message_id: int) -> Message:
    stmt = (
        select(Message).options(selectinload(Message.attachments)).where(Message.id == message_id)
    )
    message = await db.scalar(stmt)
    if not message:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    return message


def _chat_read(chat: Chat, status: ChatStatus) -> ChatRead:
    return ChatRead.model_validate(chat).model_copy(update={"status": status})


@router.get("", response_model=list[ChatRead])
async def list_chats(db: DbSession, user: CurrentUser, q: str = Query("", max_length=200)):
    chats = (await db.scalars(owned_chat_query(user.user_id, q))).all()
    statuses = await _chat_statuses(db, [c.id for c in chats])
    return [_chat_read(c, statuses.get(c.id, "draft")) for c in chats]


@router.post("", response_model=ChatRead, status_code=201)
async def create_chat(payload: ChatCreate, db: DbSession, user: CurrentUser):
    chat = Chat(title=payload.title, owner_id=user.user_id)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return _chat_read(chat, "draft")


@router.get("/{chat_id}", response_model=ChatRead)
async def get_chat(chat_id: int, db: DbSession, user: CurrentUser):
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id))
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    statuses = await _chat_statuses(db, [chat.id])
    return _chat_read(chat, statuses.get(chat.id, "draft"))


@router.get("/{chat_id}/messages", response_model=list[MessageRead])
async def list_messages(chat_id: int, db: DbSession, user: CurrentUser):
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id))
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")

    stmt = (
        select(Message)
        .options(selectinload(Message.attachments))
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    )
    result = await db.scalars(stmt)
    return [MessageRead.model_validate(message) for message in result.all()]


@router.get("/{chat_id}/messages/{message_id}", response_model=MessageRead)
async def get_message(chat_id: int, message_id: int, db: DbSession, user: CurrentUser):
    """Poll target while an analysis is running (status / stage / result)."""
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id))
    if chat is None:
        raise HTTPException(404, "Дело не найдено")
    message = await load_message(db, message_id)
    if message.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    return MessageRead.model_validate(message)


@router.post(
    "/{chat_id}/messages/{message_id}/recalculate", response_model=MessageRead, status_code=202
)
async def recalculate_message(
    chat_id: int,
    message_id: int,
    db: DbSession,
    background: BackgroundTasks,
    user: CurrentUser,
):
    """Re-run the stored exchange with the current engine; the old result is replaced (T43)."""
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id).with_for_update()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    message = await load_message(db, message_id)
    if message.chat_id != chat_id or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    if message.request_message_id is None:
        raise HTTPException(
            status_code=422, detail="У сообщения нет исходного запроса для пересчёта"
        )
    active = await db.scalar(
        select(Message.id)
        .where(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.status.in_(("pending", "running")),
        )
        .limit(1)
    )
    if active is not None:
        raise HTTPException(409, "Дождитесь завершения текущего анализа")
    message.status = "pending"
    message.stage = None
    message.error = None
    message.analysis = None
    message.content = None
    await db.commit()
    await db.refresh(message)
    background.add_task(
        run_analysis,
        message.request_message_id,
        message.id,
        user=user,
        save_to_knowledge_base=False,
        use_knowledge_base=True,
    )
    return MessageRead.model_validate(message)


@router.post("/{chat_id}/messages", response_model=MessageSendResponse, status_code=202)
async def create_message(
    chat_id: int,
    db: DbSession,
    background: BackgroundTasks,
    user: CurrentUser,
    content: str | None = Form(None),
    use_knowledge_base: bool = Form(False),
    save_to_knowledge_base: bool = Form(False),
    files: list[UploadFile] = File(default_factory=list),
):
    """Store the request and files, then analyse in the background (202 + poll)."""
    chat = await db.scalar(
        select(Chat).where(Chat.id == chat_id, Chat.owner_id == user.user_id).with_for_update()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    active = await db.scalar(
        select(Message.id)
        .where(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.status.in_(("pending", "running")),
        )
        .limit(1)
    )
    if active is not None:
        raise HTTPException(409, "Дождитесь завершения текущего анализа")
    if not (content and content.strip()) and not files:
        raise HTTPException(status_code=422, detail="Нужен текст запроса или хотя бы один файл")
    for file in files:  # reject the whole request before writing anything
        validate_extension(file.filename)

    user_message = Message(chat_id=chat_id, role="user", content=content, status="completed")
    db.add(user_message)
    await db.flush()

    stored_paths = []
    t_save_start = time.monotonic()
    try:
        for file in files:
            stored_path, size = await save_upload_file(file)
            stored_paths.append(stored_path)
            db.add(
                Attachment(
                    message_id=user_message.id,
                    filename=file.filename or "file",
                    content_type=file.content_type,
                    size=size,
                    stored_path=str(stored_path),
                    extraction_status="ok",
                )
            )

        assistant_message = Message(
            chat_id=chat_id, role="assistant", status="pending", request_message_id=user_message.id
        )
        db.add(assistant_message)
        # Chat.updated_at's onupdate only fires on changes to the chat row itself.
        await db.execute(update(Chat).where(Chat.id == chat_id).values(updated_at=func.now()))
        await db.commit()
        save_sec = time.monotonic() - t_save_start
        logger.info(
            "[API] Chat %d: user_message=%d (%d files, %.2fs), dispatched assistant_message=%d",
            chat_id,
            user_message.id,
            len(files),
            save_sec,
            assistant_message.id,
        )
    except BaseException:
        await db.rollback()
        for path in stored_paths:
            path.unlink(missing_ok=True)
        raise

    background.add_task(
        run_analysis,
        user_message.id,
        assistant_message.id,
        user=user,
        save_to_knowledge_base=save_to_knowledge_base,
        use_knowledge_base=use_knowledge_base,
    )

    return MessageSendResponse(
        user_message=MessageRead.model_validate(await load_message(db, user_message.id)),
        assistant_message=MessageRead.model_validate(await load_message(db, assistant_message.id)),
    )


@router.delete("/{chat_id}")
async def remove_chat(chat_id: int, db: DbSession, user: CurrentUser):
    try:
        return await delete_chat(SqlChatDeletionRepository(db), user.user_id, chat_id)
    except ChatNotFound:
        raise HTTPException(404, "Чат не найден") from None
    except AnalysisInProgress:
        raise HTTPException(409, "Дождитесь завершения анализа перед удалением чата") from None


@router.patch("/{chat_id}/pin", response_model=ChatRead)
async def set_chat_pin(chat_id: int, payload: ChatPin, db: DbSession, user: CurrentUser):
    try:
        await pin_chat(SqlChatPinRepository(db), user.user_id, chat_id, payload.pinned)
    except ChatNotFound:
        raise HTTPException(404, "Чат не найден") from None
    return await get_chat(chat_id, db, user)
