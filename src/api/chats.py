from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import CurrentUser, DbSession
from src.db.models import Attachment, Chat, Message
from src.infrastructure.chat_queries import owned_chat_query
from src.schemas.chat import ChatCreate, ChatRead, ChatStatus
from src.schemas.message import MessageRead, MessageSendResponse
from src.services.analysis_runner import run_analysis
from src.services.file_reader import save_upload_file, validate_extension

router = APIRouter()

_STATUS_MAP: dict[str | None, ChatStatus] = {
    None: "draft",
    "pending": "busy",
    "running": "busy",
    "completed": "ready",
    "failed": "failed",
}


async def load_message(db: AsyncSession, message_id: int) -> Message:
    stmt = (
        select(Message).options(selectinload(Message.attachments)).where(Message.id == message_id)
    )
    message = await db.scalar(stmt)
    if not message:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    return message


async def _chat_statuses(db: AsyncSession, chat_ids: list[int]) -> dict[int, ChatStatus]:
    if not chat_ids:
        return {}
    # Latest assistant message per chat; ids are monotonic, so max(id) is the newest one.
    latest_ids = (
        select(func.max(Message.id))
        .where(Message.chat_id.in_(chat_ids), Message.role == "assistant")
        .group_by(Message.chat_id)
    )
    rows = (
        await db.execute(select(Message.chat_id, Message.status).where(Message.id.in_(latest_ids)))
    ).all()
    return {chat_id: _STATUS_MAP.get(status, "draft") for chat_id, status in rows}


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
    if not (content and content.strip()) and not files:
        raise HTTPException(status_code=422, detail="Нужен текст запроса или хотя бы один файл")
    for file in files:  # reject the whole request before writing anything
        validate_extension(file.filename)

    user_message = Message(chat_id=chat_id, role="user", content=content, status="completed")
    db.add(user_message)
    await db.flush()

    stored_paths = []
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
