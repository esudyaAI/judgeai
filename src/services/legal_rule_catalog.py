"""Application Layer — справка по правилам проверки (T15.1, T15.3, T15.4).

Соединяет каталог правил ядра (legal_core.catalog) с основаниями из БД: какие снимки норм
связаны с правилом (legal_rule_references), их происхождение и статус сверки. Связи заводит
только явная административная команда; отсутствие основания показывается, а не скрывается.

T15.3 — основание на дату (например, дату преступления). Период действия нормы берётся из БД
(`legal_provisions.effective_from`/`effective_to`, та же полуоткрытая граница, что в
`GET /api/legal/lookup`): норма, не действовавшая на дату, основание не закрывает, а норма без
заданного начала действия не выдаётся за действующую. Какая редакция применима к деянию
(ст. 9–10 УК РФ) — юридическое решение T23; здесь только честный показ данных.

T15.4 — версия справки. `basis_version` правила — SHA-256 канонического JSON его описания без
даты запроса (правило ядра, связи, нормы, редакции, статусы сверки, периоды); `catalog_version` —
SHA-256 списка пар «ключ правила, basis_version». Версия не зависит от `on` и меняется при любом
изменении основания; отчёт (T14) хранит её, чтобы сверить, по какой справке сделан вывод.
"""

import hashlib
import json
from datetime import date

from legal_core import catalog
from legal_core.catalog import NormLocator, RuleDescriptor
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.db.models import LegalAct, LegalEdition, LegalProvision, LegalRuleReference

_EDITION_METADATA = (defer(LegalEdition.source_bytes), defer(LegalEdition.full_text))


def _iso(value: object) -> str:
    if isinstance(value, date):  # datetime is a subclass of date
        return value.isoformat()
    raise TypeError(f"not serializable: {type(value).__name__}")


def fingerprint(value: object) -> str:
    """SHA-256 of canonical JSON (sorted keys, dates in ISO 8601): equal data, equal version."""
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_iso
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def basis_status(statuses: set[str], missing: list[dict]) -> str:
    """Overall basis of a rule: the weakest referenced edition wins, then coverage of its norms."""
    if not statuses:
        return "no_basis"
    if "rejected" in statuses:
        return "rejected"
    if statuses != {"verified"}:
        return "unreviewed"
    return "incomplete" if missing else "verified"


def in_force_on(start: date | None, end: date | None, on: date) -> bool | None:
    """Was a provision in force on `on`: start inclusive, end exclusive; unknown start -> None."""
    if end is not None and end <= on:
        return False
    if start is None:
        return None
    return start <= on


def basis_status_on(references: list[dict], missing: list[dict], undated: list[dict]) -> str:
    """Basis on a date. `references` carry `in_force_on`; those known out of force do not count.

    No links -> `no_basis`; every link out of force -> `outdated`; otherwise the usual status
    over the usable links, and a basis that would be `verified` but rests on a norm without a
    known start of force is `period_unknown`, not `verified`.
    """
    if not references:
        return "no_basis"
    usable = [item for item in references if item["in_force_on"] is not False]
    if not usable:
        return "outdated"
    status = basis_status({item["verification_status"] for item in usable}, missing)
    return "period_unknown" if status == "verified" and undated else status


async def _references(db: AsyncSession, keys: list[str]) -> dict[str, list[dict]]:
    rows = (
        await db.execute(
            select(LegalRuleReference, LegalProvision, LegalEdition, LegalAct)
            .options(*_EDITION_METADATA)
            .join(LegalProvision, LegalRuleReference.provision_id == LegalProvision.id)
            .join(LegalEdition, LegalProvision.edition_id == LegalEdition.id)
            .join(LegalAct, LegalEdition.act_id == LegalAct.id)
            .where(LegalRuleReference.rule_key.in_(keys))
            .order_by(LegalAct.key, LegalProvision.ordinal, LegalEdition.id)
        )
    ).all()
    found: dict[str, list[dict]] = {key: [] for key in keys}
    for reference, provision, edition, act in rows:
        found[reference.rule_key].append(
            {
                "id": reference.id,
                "rationale": reference.rationale,
                "act": act.key,
                "act_title": act.title,
                "provision_id": provision.id,
                "locator": provision.locator,
                "title": provision.title,
                "effective_from": provision.effective_from,
                "effective_to": provision.effective_to,
                "edition_id": edition.id,
                "edition_label": edition.label,
                "source_url": edition.source_url,
                "source_sha256": edition.source_sha256,
                "retrieved_at": edition.retrieved_at,
                "verification_status": edition.verification_status,
            }
        )
    return found


def _norm(norm: NormLocator) -> dict:
    return {"act": norm.act, "locator": norm.locator}


def _uncovered(rule: RuleDescriptor, references: list[dict]) -> list[dict]:
    covered = {(item["act"], item["locator"]) for item in references}
    return [_norm(norm) for norm in rule.norms if (norm.act, norm.locator) not in covered]


def _describe(rule: RuleDescriptor, references: list[dict], on: date | None = None) -> dict:
    head = {
        "key": rule.key,
        "title": rule.title,
        "needs_legal_review": rule.needs_legal_review,
        "not_modelled": rule.not_modelled,
        "norms": [_norm(norm) for norm in rule.norms],
    }
    if on is None:
        missing = _uncovered(rule, references)
        statuses = {item["verification_status"] for item in references}
        return {
            **head,
            "basis_status": basis_status(statuses, missing),
            "missing_norms": missing,
            "references": references,
        }
    dated = [
        {**item, "in_force_on": in_force_on(item["effective_from"], item["effective_to"], on)}
        for item in references
    ]
    missing = _uncovered(rule, [item for item in dated if item["in_force_on"] is not False])
    unconfirmed = _uncovered(rule, [item for item in dated if item["in_force_on"]])
    undated = [norm for norm in unconfirmed if norm not in missing]
    return {
        **head,
        "on": on,
        "basis_status": basis_status_on(dated, missing, undated),
        "missing_norms": missing,
        "undated_norms": undated,
        "references": dated,
    }


def _versioned(references: dict[str, list[dict]], on: date | None) -> list[dict]:
    """Describe every rule on `on`; versions are always taken from the undated description."""
    versions = {
        rule.key: fingerprint(_describe(rule, references[rule.key])) for rule in catalog.RULES
    }
    catalog_version = fingerprint([[key, version] for key, version in versions.items()])
    return [
        {
            **_describe(rule, references[rule.key], on),
            "basis_version": versions[rule.key],
            "catalog_version": catalog_version,
        }
        for rule in catalog.RULES
    ]


async def rule_catalog(db: AsyncSession, on: date | None = None) -> list[dict]:
    return _versioned(await _references(db, [rule.key for rule in catalog.RULES]), on)


async def rule_basis(db: AsyncSession, key: str, on: date | None = None) -> dict | None:
    """One rule; the catalog version needs every rule, so the whole (small) catalog is read."""
    if catalog.find(key) is None:
        return None
    return next(item for item in await rule_catalog(db, on) if item["key"] == key)


async def link_rule(
    db: AsyncSession,
    rule_key: str,
    act_key: str,
    edition_id: int,
    locator: str,
    rationale: str,
) -> tuple[LegalRuleReference, bool]:
    """Link a rule to one provision of a stored snapshot; repeating the link changes nothing."""
    if catalog.find(rule_key) is None:
        raise ValueError("unknown rule key")
    if not rationale.strip():
        raise ValueError("rationale is empty")
    edition = await db.get(LegalEdition, edition_id, options=_EDITION_METADATA)
    if edition is None:
        raise ValueError("edition not found")
    act = await db.get(LegalAct, edition.act_id)
    if act.key != act_key:
        raise ValueError("edition belongs to another act")
    provision = await db.scalar(
        select(LegalProvision).where(
            LegalProvision.edition_id == edition_id, LegalProvision.locator == locator
        )
    )
    if provision is None:
        raise ValueError("provision not found in edition")
    reference_id = await db.scalar(
        insert(LegalRuleReference)
        .values(rule_key=rule_key, provision_id=provision.id, rationale=rationale.strip())
        .on_conflict_do_nothing(constraint="uq_legal_rule_reference")
        .returning(LegalRuleReference.id)
    )
    created = reference_id is not None
    reference = await db.scalar(
        select(LegalRuleReference).where(
            LegalRuleReference.rule_key == rule_key,
            LegalRuleReference.provision_id == provision.id,
        )
    )
    return reference, created
