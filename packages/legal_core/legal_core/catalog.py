"""Domain Layer — каталог правил проверки legal_core (T15.1).

Перечень того, какие правила реализованы в коде и на какие статьи УК РФ каждое опирается. Это
логика ядра, а не правовые данные (ключ правила — константа RULE_KEY модуля, его же несёт
CheckResult, T15.2): текст, редакции и периоды действия норм хранятся в БД
(legal_editions / legal_provisions), а конкретное основание правила — связь в
legal_rule_references, которую заводит импорт после сверки (T23). Без связи правило в справке
показывается как «без подтверждённого основания», а не скрывается.
"""

from dataclasses import dataclass

from legal_core.rules import art15, art18, art58, art62, art63, art68, art73, art86, imposed_term

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
        not_modelled="Не смоделированы ч. 2, 2.1 и 4 ст. 58 УК РФ (тюрьма, изменение вида).",
        needs_legal_review=art58.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art62.RULE_KEY,
        title="Смягчающие обстоятельства: ч. 1 ст. 62 УК РФ",
        norms=_uk("62", "61"),
        not_modelled="Не смоделированы ч. 3 и ч. 5 ст. 62 и соотношение со ст. 66 УК РФ.",
        needs_legal_review=art62.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art63.RULE_KEY,
        title=art63.NORM,
        norms=_uk("63", "18"),
        not_modelled="Ч. 1.1 и остальные пункты ч. 1 ст. 63 УК РФ не проверяются.",
        needs_legal_review=art63.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art68.RULE_KEY,
        title=art68.NORM,
        norms=_uk("68", "18"),
        not_modelled=(
            "Ст. 66 УК РФ (неоконченное преступление) не смоделирована — максимум передаёт "
            "вызывающий; ч. 1 ст. 68 машинно не проверяется."
        ),
        needs_legal_review=art68.NEEDS_LEGAL_REVIEW,
    ),
    RuleDescriptor(
        key=art73.RULE_KEY,
        title=art73.NORM,
        norms=_uk("73", "18"),
        not_modelled=(
            "Пп. «а», «а1», «б» ч. 1 ст. 73 УК РФ и общие пределы ч. 1 (виды наказания, "
            "лишение свободы до восьми лет) не проверяются."
        ),
        needs_legal_review=art73.NEEDS_LEGAL_REVIEW,
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
