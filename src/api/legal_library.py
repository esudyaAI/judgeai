"""Public source catalogue. Editing and legal verification are not HTTP operations."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import defer

from src.api.deps import DbSession
from src.db.models import LegalAct, LegalEdition, LegalProvision, LegalRuleReference
from src.schemas.legal_library import ActRead

router = APIRouter()

EDITION_METADATA = (defer(LegalEdition.source_bytes), defer(LegalEdition.full_text))


def edition_meta(edition: LegalEdition) -> dict:
    return {
        "id": edition.id,
        "act_id": edition.act_id,
        "label": edition.label,
        "source_url": edition.source_url,
        "source_sha256": edition.source_sha256,
        "retrieved_at": edition.retrieved_at,
        "parser_version": edition.parser_version,
        "verification_status": edition.verification_status,
    }


def provision_read(provision: LegalProvision) -> dict:
    return {
        "id": provision.id,
        "edition_id": provision.edition_id,
        "locator": provision.locator,
        "title": provision.title,
        "body": provision.body,
        "ordinal": provision.ordinal,
        "start_page": provision.start_page,
        "end_page": provision.end_page,
        "effective_from": provision.effective_from,
        "effective_to": provision.effective_to,
    }


@router.get("/status")
async def library_status(db: DbSession):
    return {
        "acts": await db.scalar(select(func.count()).select_from(LegalAct)),
        "editions": await db.scalar(select(func.count()).select_from(LegalEdition)),
        "provisions": await db.scalar(select(func.count()).select_from(LegalProvision)),
        "verified_editions": await db.scalar(
            select(func.count())
            .select_from(LegalEdition)
            .where(LegalEdition.verification_status == "verified")
        ),
        "rule_references": await db.scalar(select(func.count()).select_from(LegalRuleReference)),
    }


@router.get("/acts")
async def list_acts(db: DbSession, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    items = (
        await db.scalars(
            select(LegalAct).order_by(LegalAct.key).offset((page - 1) * size).limit(size)
        )
    ).all()
    return {
        "total": await db.scalar(select(func.count()).select_from(LegalAct)),
        "page": page,
        "size": size,
        "items": [ActRead.model_validate(a) for a in items],
    }


@router.get("/acts/{key}/editions")
async def list_editions(
    key: str, db: DbSession, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
):
    act = await db.scalar(select(LegalAct).where(LegalAct.key == key))
    if act is None:
        raise HTTPException(404, "Акт не найден")
    condition = LegalEdition.act_id == act.id
    items = (
        await db.scalars(
            select(LegalEdition)
            .options(*EDITION_METADATA)
            .where(condition)
            .order_by(LegalEdition.retrieved_at.desc(), LegalEdition.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return {
        "total": await db.scalar(select(func.count()).select_from(LegalEdition).where(condition)),
        "page": page,
        "size": size,
        "items": [edition_meta(e) for e in items],
    }


@router.get("/editions/{edition_id}/provisions")
async def list_provisions(
    edition_id: int,
    db: DbSession,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, min_length=2, max_length=200),
):
    edition = await db.get(LegalEdition, edition_id, options=EDITION_METADATA)
    if edition is None:
        raise HTTPException(404, "Редакция не найдена")
    conditions = [LegalProvision.edition_id == edition_id]
    if q:
        conditions.append(
            or_(
                LegalProvision.title.contains(q, autoescape=True),
                LegalProvision.body.contains(q, autoescape=True),
            )
        )
    items = (
        await db.scalars(
            select(LegalProvision)
            .where(*conditions)
            .order_by(LegalProvision.ordinal)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return {
        **edition_meta(edition),
        "total": await db.scalar(
            select(func.count()).select_from(LegalProvision).where(*conditions)
        ),
        "page": page,
        "size": size,
        "items": [provision_read(p) for p in items],
    }


@router.get("/lookup")
async def lookup_provision(
    db: DbSession,
    act: str = Query(min_length=1, max_length=80),
    locator: str = Query(min_length=1, max_length=160),
    on_date: date = Query(alias="on"),
):
    rows = (
        await db.execute(
            select(LegalProvision, LegalEdition)
            .options(*EDITION_METADATA)
            .join(LegalEdition, LegalProvision.edition_id == LegalEdition.id)
            .join(LegalAct, LegalEdition.act_id == LegalAct.id)
            .where(
                LegalAct.key == act,
                LegalProvision.locator == locator,
                LegalEdition.verification_status == "verified",
                LegalProvision.effective_from <= on_date,
                or_(LegalProvision.effective_to.is_(None), LegalProvision.effective_to > on_date),
            )
            .limit(2)
        )
    ).all()
    if not rows:
        raise HTTPException(404, "Нет проверенной нормы, действующей на эту дату")
    if len(rows) > 1:
        raise HTTPException(
            409, "Проверенные нормы противоречат друг другу; нужна юридическая проверка"
        )
    provision, edition = rows[0]
    return {
        **provision_read(provision),
        **{k: v for k, v in edition_meta(edition).items() if k != "id"},
    }
