"""Domain Layer — каталог правил проверки legal_core (T15.1).

Перечень того, какие правила реализованы в коде и на какие статьи УК РФ каждое опирается. Это
логика ядра, а не правовые данные (ключ правила — константа RULE_KEY модуля, его же несёт
CheckResult, T15.2): текст, редакции и периоды действия норм хранятся в БД
(legal_editions / legal_provisions), а конкретное основание правила — связь в
legal_rule_references, которую заводит импорт после сверки (T23). Без связи правило в справке
показывается как «без подтверждённого основания», а не скрывается.
"""

from dataclasses import dataclass

from legal_core.rules import (
    art15,
    art18,
    art58,
    art58_prison,
    art62,
    art63,
    art66,
    art68,
    art70,
    art73,
    art86,
    imposed_term,
)

CRIMINAL_CODE = "uk-rf"


@dataclass(frozen=True)
class NormLocator:
    """Article of an act as it is addressed in the legal library (act key + provision locator)."""

    act: str
    locator: str


@dataclass(frozen=True)
class RuleDescriptor:
    key: str
    title: str
    norms: tuple[NormLocator, ...]
    not_modelled: str
    needs_legal_review: bool = True


def _uk(*articles: str) -> tuple[NormLocator, ...]:
    return tuple(NormLocator(CRIMINAL_CODE, f"article.{number}") for number in articles)


RULES: tuple[RuleDescriptor, ...] = (
    RuleDescriptor(
        key=art15.RULE_KEY,
        title="Категория преступления: ч. 2–6 ст. 15 УК РФ",
        norms=_uk("15"),
        not_modelled=(
            "Редакция на дату преступления не выбирается (ст. 9–10 УК РФ); изменение "
            "категории по ч. 6 ст. 15 решает суд."
        ),
    ),
    RuleDescriptor(
        key=art18.RULE_KEY,
        title="Вид рецидива: ч. 1–4 ст. 18 УК РФ",
        norms=_uk("18", "86"),
        not_modelled=(
            "Наличие судимости на дату преступления и редакцию нормы на эту дату передаёт "
            "вызывающий; неизвестное даёт «не решено»."
        ),
    ),
    RuleDescriptor(
        key=art58.RULE_KEY,
        title=art58.NORM,
        norms=_uk("58"),
        not_modelled=(
            "Не смоделирована ч. 4 ст. 58 УК РФ (изменение вида); часть срока в тюрьме — "
            "отдельное правило art58.prison_part."
        ),
        needs_legal_review=art58.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art58_prison.RULE_KEY,
        title=art58_prison.NORM,
        norms=_uk("58"),
        not_modelled=(
            "Перечни статей ч. 2 и 2.1 ст. 58 УК РФ сообщает вызывающий; п. 7 ППВС № 9 "
            "(новое преступление во время отбывания в тюрьме) — отдельное правило."
        ),
        needs_legal_review=art58_prison.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art58_prison.NEW_OFFENCE_RULE_KEY,
        title=art58_prison.NEW_OFFENCE_NORM,
        norms=_uk("58", "70"),
        not_modelled=(
            "Неотбытую часть наказания в тюрьме по предыдущему приговору и место совершения "
            "преступления передаёт вызывающий; правильность выбора вида учреждения для "
            "оставшейся части проверяет правило art58.institution."
        ),
        needs_legal_review=art58_prison.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art62.RULE_KEY,
        title="Смягчающие обстоятельства: ч. 1 ст. 62 УК РФ",
        norms=_uk("62", "61"),
        not_modelled=(
            "Ч. 3 ст. 62 учитывается по данным санкции; соотношение с ч. 5 ст. 62 и ст. 66 УК РФ "
            "не смоделировано."
        ),
        needs_legal_review=art62.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art62.RULE_KEY_PART5,
        title=art62.NORM_PART5,
        norms=_uk("62"),
        not_modelled=(
            "Порядок рассмотрения передаёт вызывающий; пределы для менее строгих видов "
            "наказания не вычисляются; ч. 2 и 4 ст. 62 УК РФ — отдельное правило "
            "art62.pretrial_agreement."
        ),
        needs_legal_review=art62.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art62.AGREEMENT_RULE_KEY,
        title=art62.AGREEMENT_NORM,
        norms=_uk("62", "61"),
        not_modelled=(
            "Действие соглашения (соблюдение условий и обязательств, порядок гл. 40.1 УПК РФ) "
            "передаёт вызывающий; пределы для менее строгих видов наказания не вычисляются; "
            "соотношение с ч. 5 ст. 62 и ст. 66 УК РФ не смоделировано."
        ),
        needs_legal_review=art62.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art63.RULE_KEY,
        title=art63.NORM,
        norms=_uk("63", "18"),
        not_modelled=(
            "Остальные пункты ч. 1 ст. 63 УК РФ не проверяются; ч. 1.1 (состояние опьянения) — "
            "отдельное правило art63.intoxication_aggravating."
        ),
        needs_legal_review=art63.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art63.INTOXICATION_RULE_KEY,
        title=art63.INTOXICATION_NORM,
        norms=_uk("63"),
        not_modelled=(
            "Признание опьянения отягчающим — право суда: достаточность мотивов по существу не "
            "оценивается; является ли опьянение признаком состава (например, ст. 264.1 УК РФ), "
            "передаёт вызывающий по квалификации и редакции на дату преступления."
        ),
        needs_legal_review=art63.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art66.RULE_KEY,
        title=art66.NORM,
        norms=_uk("66", "30"),
        not_modelled=(
            "Ч. 1 ст. 66 УК РФ машинно не проверяется; стадию (ст. 30) передаёт вызывающий; "
            "пределы для менее строгих видов наказания и санкции с пожизненным лишением "
            "свободы или смертной казнью не вычисляются."
        ),
        needs_legal_review=art66.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art68.RULE_KEY,
        title=art68.NORM,
        norms=_uk("68", "18"),
        not_modelled=(
            "Максимум для неоконченного преступления (ст. 66 УК РФ) передаёт вызывающий — "
            "правило art66; ч. 1 ст. 68 машинно не проверяется."
        ),
        needs_legal_review=art68.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art73.RULE_KEY,
        title=art73.NORM,
        norms=_uk("73", "18"),
        not_modelled=(
            "Перечни преступлений (пп. «а» и «а1»), п. «б» и пределы ч. 1 ст. 73 УК РФ "
            "(виды наказания, лишение свободы до восьми лет) — отдельные правила."
        ),
        needs_legal_review=art73.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art73.LIMITS_RULE_KEY,
        title=art73.LIMITS_NORM,
        norms=_uk("73"),
        not_modelled=(
            "Вид и срок итогового наказания передаёт вызывающий; «до восьми лет» понимается "
            "включительно — толкование на сверку T23."
        ),
        needs_legal_review=art73.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art73.SUPERVISION_RULE_KEY,
        title=art73.SUPERVISION_NORM,
        norms=_uk("73", "79"),
        not_modelled=(
            "Периоды условного осуждения и условно-досрочного освобождения передаёт вызывающий; "
            "день начала и окончания периода считается недостаточностью данных."
        ),
        needs_legal_review=art73.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art73.OFFENCE_LIST_RULE_KEY,
        title=art73.OFFENCE_LIST_NORM,
        norms=_uk("73"),
        not_modelled=(
            "Отнесение каждого преступления к перечням передаёт вызывающий: перечень п. «а1» "
            "зависит от редакции на дату преступления (последнее изменение — ФЗ от 17.11.2025 "
            "N 420-ФЗ), возраст потерпевшего для п. «а» — факт дела."
        ),
        needs_legal_review=art73.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art70.RULE_KEY,
        title=art70.NORM,
        norms=_uk("70", "56"),
        not_modelled=(
            "Отнесение преступления к перечню ч. 5 ст. 56 УК РФ, сроки по последнему приговору "
            "и неотбытую часть (с пересчётом по ст. 71) передаёт вызывающий; ч. 1, ч. 2 (менее "
            "строгие виды) и ч. 5 ст. 70 УК РФ не смоделированы."
        ),
        needs_legal_review=art70.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art86.RULE_KEY,
        title="Погашение судимости: ч. 1–4 ст. 86, ст. 95 УК РФ",
        norms=_uk("86", "95"),
        not_modelled=(
            "Снятие судимости (ч. 3.1 и 5 ст. 86 УК РФ) не вычисляется — дату передаёт вызывающий."
        ),
        needs_legal_review=art86.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=imposed_term.RULE_KEY,
        title=imposed_term.NORM,
        norms=_uk("62"),
        not_modelled=imposed_term.NOT_COVERED,
    ),
)

_BY_KEY = {item.key: item for item in RULES}


def find(key: str) -> RuleDescriptor | None:
    return _BY_KEY.get(key)


def rule(key: str) -> RuleDescriptor:
    """Descriptor of a rule; an unknown key is an error, never a default rule."""
    return _BY_KEY[key]
