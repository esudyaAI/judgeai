"""Background execution of a case analysis.

The request handler stores the files and returns immediately with an assistant message in
status "pending"; this runner then walks the stages and updates the message so the UI can poll:
    reading -> searching -> qualifying -> checking -> completed | failed
(similar verdicts are searched before the LLM call because they are part of its prompt)
"""

import logging
import time
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from src.application.practice_report import compare_draft_with_practice
from src.application.precedent_cards import query_card
from src.config import settings
from src.db import session as db_session
from src.db.auth import User
from src.db.models import Chat, Message
from src.domain.documents import UnreadableInput, reading_warnings
from src.infrastructure.conversation import load_conversation
from src.infrastructure.fastembed_embedder import FastembedEmbedder
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.infrastructure.verdict_reader import RegexVerdictReader
from src.services.analysis_access import is_pending_reply
from src.services.auth import UserContext
from src.services.case_analyzer import (
    DOCUMENT_CHARS_LIMIT,
    assemble_analysis,
    extract_facts,
    precedent_prompt_items,
)
from src.services.criminal_sanction_lookup import find_article_sanctions
from src.services.document_parser import extract_document
from src.services.knowledge_service import create_knowledge_verdict_from_text
from src.services.llm_client import LLMError, get_llm_client
from src.services.punishment_window_resolver import resolve_windows
from src.services.qualification_reference import parse_qualification_reference
from src.services.similarity_search import find_similar_verdicts
from src.services.verdict_structure import read_verdict_structure

logger = logging.getLogger(__name__)

INTERRUPTED_ERROR = "Анализ прерван перезапуском сервера"


async def _set_stage(message_id: int, *, status: str = "running", stage: str | None = None) -> None:
    async with db_session.async_session_factory() as db:
        await db.execute(
            update(Message).where(Message.id == message_id).values(status=status, stage=stage)
        )
        await db.commit()


def get_precedent_embedder() -> FastembedEmbedder:
    return FastembedEmbedder()


async def _search_practice(db, question: str, texts: list[str]):
    """Precedent cards first (T24–T28); the free-text search only when there are no cards
    yet or the draft gave no text to read a card from. Returns (prompt items, report, source)."""
    store = SqlPrecedentStore(db)
    query = query_card(RegexVerdictReader(), texts)
    if query is not None and await store.has_cards():
        report = await compare_draft_with_practice(store, get_precedent_embedder(), query)
        return precedent_prompt_items(report), report, "cards"
    items = await find_similar_verdicts(db=db, query_text=question, document_texts=texts)
    return items, None, "text" if items else "none"


async def run_analysis(
    user_message_id: int,
    assistant_message_id: int,
    *,
    user: UserContext,
    save_to_knowledge_base: bool = False,
    use_knowledge_base: bool = True,
) -> None:
    # Validate before any status mutation, document read or external model call.
    async with db_session.async_session_factory() as db:
        account = await db.get(User, user.user_id)
        request = await db.get(Message, user_message_id)
        result = await db.get(Message, assistant_message_id)
        chat = await db.get(Chat, request.chat_id) if request else None
        if (
            account is None
            or not account.is_active
            or chat is None
            or chat.owner_id != user.user_id
            or result is None
            or not is_pending_reply(request, result)
        ):
            logger.warning("rejected unauthorized analysis job")
            return
        claimed = await db.scalar(
            update(Message)
            .where(
                Message.id == assistant_message_id,
                Message.request_message_id == user_message_id,
                Message.status == "pending",
            )
            .values(status="running", stage="reading")
            .returning(Message.id)
        )
        await db.commit()
        if claimed is None:
            return
    started = time.monotonic()
    try:
        async with db_session.async_session_factory() as db:
            user_message = await db.scalar(
                select(Message)
                .options(selectinload(Message.attachments))
                .where(Message.id == user_message_id)
            )
            if user_message is None:
                raise RuntimeError("user message disappeared")

            texts: list[str] = []
            pages = 0
            warnings: list[str] = []
            if settings.LLM_PROVIDER == "fake":
                warnings.append(
                    "Режим разработки: показан фиксированный синтетический пример, а не анализ "
                    "загруженных документов. Для настоящего анализа подключите языковую модель."
                )
            for att in user_message.attachments:
                doc = await extract_document(Path(att.stored_path))
                att.extracted_text = doc.text
                att.page_count = doc.page_count
                att.extraction_status = doc.status
                texts.append(doc.text)
                pages += doc.page_count or 0
                if doc.status in ("partial", "empty", "error"):
                    warnings.append(f"«{att.filename}»: текст распознан {_status_ru(doc.status)}.")
                warnings.extend(f"{att.filename}: {warning}" for warning in reading_warnings(doc))
                if save_to_knowledge_base and doc.text.strip():
                    await create_knowledge_verdict_from_text(
                        db=db, filename=att.filename, raw_text=doc.text, source_type="chat"
                    )
            question = user_message.content
            chat_id = user_message.chat_id
            documents = len(user_message.attachments)
            context = await load_conversation(db, user.user_id, chat_id, user_message_id, question)
            texts.extend(document.text for document in context.documents)
            pages += sum(document.pages for document in context.documents)
            documents += len(context.documents)
            warnings.extend(context.warnings)
            await db.commit()

        if not (question or "").strip() and not any(text.strip() for text in texts):
            raise UnreadableInput(
                "Читаемый текст не найден. Загрузите документ с текстом или задайте вопрос."
            )

        await _set_stage(assistant_message_id, stage="searching")
        similar_items: list[dict] = []
        practice = precedent_source = None
        if use_knowledge_base:
            async with db_session.async_session_factory() as db:
                similar_items, practice, precedent_source = await _search_practice(
                    db, question or "", texts
                )

        await _set_stage(assistant_message_id, stage="qualifying")
        llm = get_llm_client()
        structure = read_verdict_structure(texts, DOCUMENT_CHARS_LIMIT)
        if sum(len(text) for text in structure.model_texts) > DOCUMENT_CHARS_LIMIT:
            warnings.append("Текст документов для модели сокращён. Проверьте оригиналы файлов.")
        facts = await extract_facts(llm, context.question, structure.model_texts, similar_items)
        sentence = structure.sentence
        if structure.ambiguous_windows and settings.LLM_PROVIDER != "fake":
            async with db_session.async_session_factory() as db:
                resolved = await resolve_windows(db, llm, structure.ambiguous_windows)
            sentence = structure.with_resolved_windows(resolved)

        await _set_stage(assistant_message_id, stage="checking")
        statute = None
        reference = parse_qualification_reference(
            facts.qualification.article if facts.qualification else None
        )
        count_references = {c.reference for c in sentence.counts if c.reference is not None}
        count_statutes = {}
        async with db_session.async_session_factory() as db:
            if reference is not None:
                statute = await find_article_sanctions(db, reference.article, reference.part)
            for count_reference in count_references:
                reading = await find_article_sanctions(
                    db, count_reference.article, count_reference.part
                )
                if reading is not None:
                    count_statutes[count_reference] = reading
        if reference is not None and statute is None:
            warnings.append(f"Санкция {reference} не найдена в импортированном тексте УК РФ.")
        analysis = assemble_analysis(
            facts,
            prompt=question or "",
            documents=documents,
            pages=pages,
            seconds=round(time.monotonic() - started),
            similar_items=similar_items,
            extra_warnings=warnings,
            document_texts=texts,
            statute=statute,
            sentence=sentence,
            count_statutes=count_statutes,
            model_texts=structure.model_texts,
            practice=practice,
            precedent_source=precedent_source,
        )

        async with db_session.async_session_factory() as db:
            await db.execute(
                update(Message)
                .where(Message.id == assistant_message_id)
                .values(
                    status="completed",
                    stage=None,
                    content=analysis.fabula,
                    analysis=analysis.model_dump(mode="json"),
                    error=None,
                )
            )
            # Untitled cases get their qualification as a title (the sidebar shows it).
            if analysis.qualification:
                await db.execute(
                    update(Chat)
                    .where(Chat.id == chat_id, Chat.title.is_(None))
                    .values(title=analysis.qualification.article[:255])
                )
            await db.commit()
    except Exception as exc:
        logger.exception("analysis failed for message %s", assistant_message_id)
        # LLMError messages are written for users; anything else is an internal error.
        error = (
            str(exc)
            if isinstance(exc, (LLMError, UnreadableInput))
            else "Внутренняя ошибка анализа"
        )
        async with db_session.async_session_factory() as db:
            await db.execute(
                update(Message)
                .where(Message.id == assistant_message_id)
                .values(status="failed", stage=None, error=error)
            )
            await db.commit()


def _status_ru(status: str) -> str:
    return {
        "partial": "частично",
        "empty": "пустым — нет текстового слоя",
        "error": "с ошибкой",
    }.get(status, status)


async def fail_interrupted_analyses() -> int:
    """BackgroundTasks die with the process: mark leftovers as failed on startup."""
    async with db_session.async_session_factory() as db:
        result = await db.execute(
            update(Message)
            .where(Message.status.in_(("pending", "running")), Message.role == "assistant")
            .values(status="failed", stage=None, error=INTERRUPTED_ERROR)
        )
        await db.commit()
        return result.rowcount or 0
