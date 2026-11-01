"""Application Layer — справка по правилам проверки (T15.1).

Соединяет каталог правил ядра (legal_core.catalog) с основаниями из БД: какие снимки норм
связаны с правилом (legal_rule_references), их происхождение и статус сверки. Связи заводит
только явная административная команда; отсутствие основания показывается, а не скрывается.
"""

from legal_core import catalog
from legal_core.catalog import RuleDescriptor
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.db.models import LegalAct, LegalEdition, LegalProvision, LegalRuleReference

_EDITION_METADATA = (defer(LegalEdition.source_bytes), defer(LegalEdition.full_text))


def basis_status(statuses: set[str], missing: list[dict]) -> str:
    """Overall basis of a rule: the weakest referenced edition wins, then coverage of its norms."""
    if not statuses:
        return "no_basis"
    if "rejected" in statuses:
        return "rejected"
    if statuses != {"verified"}:
        return "unreviewed"
    return "incomplete" if missing else "verified"


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


def _describe(rule: RuleDescriptor, references: list[dict]) -> dict:
    covered = {(item["act"], item["locator"]) for item in references}
    missing = [
        {"act": norm.act, "locator": norm.locator}
        for norm in rule.norms
        if (norm.act, norm.locator) not in covered
    ]
    statuses = {item["verification_status"] for item in references}
    return {
        "key": rule.key,
        "title": rule.title,
        "needs_legal_review": rule.needs_legal_review,
        "not_modelled": rule.not_modelled,
        "norms": [{"act": norm.act, "locator": norm.locator} for norm in rule.norms],
        "basis_status": basis_status(statuses, missing),
        "missing_norms": missing,
        "references": references,
    }


async def rule_catalog(db: AsyncSession) -> list[dict]:
    references = await _references(db, [rule.key for rule in catalog.RULES])
    return [_describe(rule, references[rule.key]) for rule in catalog.RULES]


async def rule_basis(db: AsyncSession, key: str) -> dict | None:
    rule = catalog.find(key)
    if rule is None:
        return None
    return _describe(rule, (await _references(db, [key]))[key])


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
