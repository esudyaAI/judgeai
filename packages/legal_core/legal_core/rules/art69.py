# Domain Layer — ч. 2 и ч. 3 ст. 69 УК РФ «Назначение наказания по совокупности преступлений»:
# ч. 2 (ред. ФЗ от 07.12.2011 N 420-ФЗ) — все преступления небольшой или средней тяжести либо
# приготовление/покушение на тяжкое или особо тяжкое: поглощение, частичное или полное сложение,
# окончательное наказание не более чем наполовину выше максимального срока или размера наказания
# за наиболее тяжкое из совершённых преступлений; ч. 3 (ред. ФЗ от 08.12.2003 N 162-ФЗ) — хотя бы
# одно оконченное тяжкое или особо тяжкое: только частичное или полное сложение, окончательное
# лишение свободы не более чем наполовину выше максимального срока лишения свободы за наиболее
# тяжкое преступление. Категория (ст. 15) и стадия (ст. 30) каждого преступления — факты дела;
# какое преступление наиболее тяжкое и максимум его санкции (из БД, с учётом ст. 66/62, если
# применимо) передаёт вызывающий. Сроки — в месяцах одного вида наказания.
# Известное нарушение выдаётся, даже если другие факты не установлены; иначе неизвестный
# значимый факт → «недостаточно данных». Толкование сверяется в T23.
# Ч. 4 (дополнительные наказания, применяется и к ст. 70 через её ч. 5) — отдельное правило
# ниже, ADDITIONAL_RULE_KEY.
# Ч. 5 (преступление до вынесения первого приговора, зачёт отбытого) — правило PRIOR_RULE_KEY.
# TODO(T4/T23): ч. 1 (наказание за каждое преступление отдельно), предел ч. 3 для видов, кроме
# лишения свободы, и размер зачёта по ч. 5 (ст. 72) не смоделированы.
from dataclasses import dataclass
from enum import StrEnum

from legal_core.checks import CheckResult, CheckStatus
from legal_core.entities import Category
from legal_core.rules.art66 import OffenceStage

NEEDS_LEGAL_REVIEW = True
RULE_KEY = "art69.offences_cumulation"
NORM = "Совокупность преступлений: ч. 2 и ч. 3 ст. 69 УК РФ"
SOURCE = (
    "УК РФ ст. 69, ч. 2 (ред. ФЗ от 07.12.2011 N 420-ФЗ) и ч. 3 (ред. ФЗ от 08.12.2003 "
    "N 162-ФЗ) — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891"
    "&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde17734e637"
    "35b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23)"
)

_GRAVE = (Category.GRAVE, Category.ESPECIALLY_GRAVE)


class CumulationMethod(StrEnum):
    """How the final punishment is formed (ч. 2–3 ст. 69 УК РФ)."""

    ABSORPTION = "absorption"
    PARTIAL_ADDITION = "partial_addition"
    FULL_ADDITION = "full_addition"


@dataclass(frozen=True)
class CumulatedOffence:
    """One offence of the cumulation; category None — not established."""

    category: Category | None
    stage: OffenceStage


@dataclass(frozen=True)
class OffencesCumulationFacts:
    """most_serious_max_months — maximum term of the punishment kind imposed (for ч. 3 —
    imprisonment) for the most serious offence; None — not established."""

    offences: tuple[CumulatedOffence, ...]
    most_serious_max_months: int | None


@dataclass(frozen=True)
class DraftOffencesCumulation:
    """What the draft imposes; None means not extracted."""

    by_cumulation: bool | None
    method: CumulationMethod | None
    final_months: int | None
    imprisonment: bool | None
    life_imprisonment: bool = False


def _completed_grave(offence: CumulatedOffence) -> bool:
    return offence.category in _GRAVE and offence.stage is OffenceStage.COMPLETED


def _may_be_completed_grave(offence: CumulatedOffence) -> bool:
    if offence.category is None:
        return True
    return offence.category in _GRAVE and offence.stage is OffenceStage.UNKNOWN


def cumulation_part(offences: tuple[CumulatedOffence, ...]) -> int | None:
    """2 or 3 — the part of ст. 69 that applies; None — not established."""
    if any(_completed_grave(offence) for offence in offences):
        return 3
    if not offences or any(_may_be_completed_grave(offence) for offence in offences):
        return None
    return 2


def exceeds_cumulation_limit(final_months: int, maximum_months: int) -> bool:
    """«Не более чем наполовину» сверх максимума: final > 1.5 × maximum, without rounding."""
    if maximum_months <= 0:
        raise ValueError("Максимальный срок должен быть положительным.")
    return 2 * final_months > 3 * maximum_months


def _result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(NORM, status, why, SOURCE, NEEDS_LEGAL_REVIEW, RULE_KEY)


def _reject_invalid(facts: OffencesCumulationFacts, draft: DraftOffencesCumulation) -> None:
    if draft.final_months is not None and draft.final_months < 0:
        raise ValueError("Срок не может быть отрицательным.")
    if facts.most_serious_max_months is not None and facts.most_serious_max_months <= 0:
        raise ValueError("Максимальный срок должен быть положительным.")


def _method_finding(
    part: int | None, method: CumulationMethod | None
) -> tuple[str | None, str | None]:
    """(violation, unknown) for the method of ч. 3 ст. 69."""
    if part == 2:
        return None, None
    if method is CumulationMethod.ABSORPTION and part == 3:
        return (
            "При тяжком или особо тяжком преступлении поглощение менее строгого наказания "
            "более строгим не допускается — только частичное или полное сложение "
            "(ч. 3 ст. 69 УК РФ).",
            None,
        )
    if method is None and part == 3:
        return None, "Не установлен способ назначения окончательного наказания."
    if part is None and method in (None, CumulationMethod.ABSORPTION):
        return None, _PART_UNKNOWN
    return None, None


_PART_UNKNOWN = (
    "Не установлены категория или стадия всех преступлений: неизвестно, есть ли среди них "
    "оконченное тяжкое или особо тяжкое (ч. 2 или ч. 3 ст. 69 УК РФ)."
)


def _limit_part(part: int | None, imprisonment: bool | None) -> tuple[str | None, str | None]:
    """(part label, unknown) — which limit applies to the final term."""
    if imprisonment is True:
        return ("ч. 2 ст. 69" if part == 2 else "ч. 3 ст. 69" if part == 3 else "ст. 69"), None
    if part == 2:
        return "ч. 2 ст. 69", None
    if part == 3 and imprisonment is False:
        return None, (
            "Предел ч. 3 ст. 69 УК РФ установлен для лишения свободы; предел для иного вида "
            "окончательного наказания не смоделирован."
        )
    if part == 3:
        return None, "Не установлен вид окончательного наказания."
    return None, _PART_UNKNOWN


def _limit_finding(
    facts: OffencesCumulationFacts, draft: DraftOffencesCumulation, part: int | None
) -> tuple[str | None, str | None]:
    """(violation, unknown) for «не более чем наполовину» of ч. 2 / ч. 3 ст. 69."""
    final = draft.final_months
    if final is None:
        return None, "В проекте не установлен срок окончательного наказания."
    label, unknown = _limit_part(part, draft.imprisonment)
    if label is None:
        return None, unknown
    maximum = facts.most_serious_max_months
    if maximum is None:
        return None, "Не установлен максимальный срок наказания за наиболее тяжкое преступление."
    if not exceeds_cumulation_limit(final, maximum):
        return None, None
    limit = f"{3 * maximum / 2:g}".replace(".", ",")
    return (
        f"Окончательное наказание {final} мес. превышает более чем наполовину максимальный срок "
        f"за наиболее тяжкое преступление ({maximum} мес., предел {limit} мес., {label} УК РФ).",
        None,
    )


def check_offences_cumulation(
    facts: OffencesCumulationFacts, draft: DraftOffencesCumulation
) -> CheckResult:
    _reject_invalid(facts, draft)
    if draft.by_cumulation is False:
        return _result(CheckStatus.OK, "Наказание по совокупности преступлений не назначается.")
    if draft.by_cumulation is None:
        return _result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначается ли наказание по совокупности преступлений.",
        )
    if draft.life_imprisonment:
        return _result(
            CheckStatus.INSUFFICIENT_DATA,
            "Назначено пожизненное лишение свободы: предел ст. 69 УК РФ в месяцах не вычисляется.",
        )
    part = cumulation_part(facts.offences)
    findings = [_method_finding(part, draft.method), _limit_finding(facts, draft, part)]
    violations = [violation for violation, _ in findings if violation]
    if violations:
        return _result(CheckStatus.POSSIBLE_VIOLATION, " ".join(violations))
    unknown = list(dict.fromkeys(gap for _, gap in findings if gap))
    if unknown:
        return _result(CheckStatus.INSUFFICIENT_DATA, " ".join(unknown))
    where = f"ч. {part} ст. 69" if part else "ст. 69"
    return _result(CheckStatus.OK, f"Окончательное наказание соответствует {where} УК РФ.")


# --- ч. 4 ст. 69 и ч. 5 ст. 70 УК РФ: дополнительные наказания при совокупности ---
# «К основным видам наказаний могут быть присоединены дополнительные виды наказаний» — право
# суда, поэтому отсутствие дополнительного наказания не замечание. «Окончательное дополнительное
# наказание при частичном или полном сложении наказаний не может превышать максимального срока
# или размера, предусмотренного для данного вида наказания Общей частью» (ч. 4 ст. 69); по
# совокупности приговоров — по тем же правилам (ч. 5 ст. 70), там наказания всегда
# присоединяются, способ не важен. Максимум каждого вида по Общей части (ст. 46, 47, 48, 53 и
# т. д. в нужной редакции) — данные, передаёт вызывающий в тех же единицах, что и размер.

ADDITIONAL_RULE_KEY = "art69.additional_punishments"
ADDITIONAL_NORM = "Дополнительные наказания при совокупности: ч. 4 ст. 69 и ч. 5 ст. 70 УК РФ"
ADDITIONAL_SOURCE = (
    "УК РФ ст. 69, ч. 4 и ст. 70, ч. 5 — официальная выгрузка http://pravo.gov.ru/proxy/ips/"
    "?savertf=&nd=102041891&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f4"
    "9077bd34fde17734e63735b87e16f4a34d7b (статус unreviewed, периоды действия сверить в T23)"
)


class CumulationBasis(StrEnum):
    """Which cumulation: of offences (ст. 69) or of sentences (ст. 70)."""

    OFFENCES = "offences"
    SENTENCES = "sentences"


@dataclass(frozen=True)
class AdditionalPunishment:
    """Final additional punishment of one kind; None — not established.

    final_amount and general_part_maximum are in the same units (months, roubles, …)."""

    kind: str
    final_amount: int | None
    general_part_maximum: int | None


@dataclass(frozen=True)
class DraftAdditionalCumulation:
    """What the draft imposes; basis/method None — not established."""

    by_cumulation: bool | None
    basis: CumulationBasis | None
    method: CumulationMethod | None
    additional: tuple[AdditionalPunishment, ...]


def _additional_result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(
        ADDITIONAL_NORM, status, why, ADDITIONAL_SOURCE, NEEDS_LEGAL_REVIEW, ADDITIONAL_RULE_KEY
    )


def _reject_invalid_additional(additional: tuple[AdditionalPunishment, ...]) -> None:
    for punishment in additional:
        if not punishment.kind.strip():
            raise ValueError("Не указан вид дополнительного наказания.")
        if punishment.final_amount is not None and punishment.final_amount < 0:
            raise ValueError("Размер наказания не может быть отрицательным.")
        if punishment.general_part_maximum is not None and punishment.general_part_maximum <= 0:
            raise ValueError("Максимум по Общей части должен быть положительным.")


def _limit_applies(draft: DraftAdditionalCumulation) -> bool | None:
    """True — limit of ч. 4 ст. 69 applies, False — absorption, None — method unknown."""
    if draft.basis is CumulationBasis.SENTENCES:
        return True
    if draft.method is CumulationMethod.ABSORPTION:
        return False
    if draft.method is None:
        return None
    return True


def _where(basis: CumulationBasis | None) -> str:
    if basis is CumulationBasis.SENTENCES:
        return "ч. 5 ст. 70 и ч. 4 ст. 69 УК РФ"
    return "ч. 4 ст. 69 УК РФ"


def check_additional_punishments(draft: DraftAdditionalCumulation) -> CheckResult:
    _reject_invalid_additional(draft.additional)
    if draft.by_cumulation is False:
        return _additional_result(CheckStatus.OK, "Наказание по совокупности не назначается.")
    if draft.by_cumulation is None:
        return _additional_result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначается ли наказание по совокупности преступлений или приговоров.",
        )
    if not draft.additional:
        return _additional_result(
            CheckStatus.OK,
            "Дополнительные наказания не назначены: их присоединение — право суда "
            "(ч. 4 ст. 69 УК РФ).",
        )
    applies = _limit_applies(draft)
    if applies is False:
        return _additional_result(
            CheckStatus.OK,
            "Наказания назначены путём поглощения: предел ч. 4 ст. 69 УК РФ установлен для "
            "частичного или полного сложения.",
        )
    where = _where(draft.basis)
    violations: list[str] = []
    unknown: list[str] = []
    for punishment in draft.additional:
        amount, maximum = punishment.final_amount, punishment.general_part_maximum
        if amount is None:
            unknown.append(f"Не установлен размер дополнительного наказания «{punishment.kind}».")
        elif maximum is None:
            unknown.append(
                f"Не установлен максимум по Общей части для наказания «{punishment.kind}»."
            )
        elif amount > maximum and applies is None:
            unknown.append(
                f"Наказание «{punishment.kind}» ({amount}) больше максимума по Общей части "
                f"({maximum}), но не установлен способ назначения окончательного наказания "
                "(сложение или поглощение)."
            )
        elif amount > maximum:
            violations.append(
                f"Окончательное дополнительное наказание «{punishment.kind}» ({amount}) превышает "
                f"максимум, предусмотренный для этого вида Общей частью УК РФ ({maximum}; {where})."
            )
    if violations:
        return _additional_result(CheckStatus.POSSIBLE_VIOLATION, " ".join(violations))
    if unknown:
        return _additional_result(CheckStatus.INSUFFICIENT_DATA, " ".join(unknown))
    return _additional_result(
        CheckStatus.OK, f"Дополнительные наказания не превышают максимумов Общей части ({where})."
    )


# --- ч. 5 ст. 69 УК РФ: преступление, совершённое до вынесения первого приговора ---
# «По тем же правилам назначается наказание, если после вынесения судом приговора по делу будет
# установлено, что осужденный виновен еще и в другом преступлении, совершенном им до вынесения
# приговора суда по первому делу. В этом случае в окончательное наказание засчитывается
# наказание, отбытое по первому приговору суда.» ППВС № 58 п. 52: значение имеет время
# вынесения первого приговора, а не вступления в силу; п. 53: к условно осуждённому ч. 5 не
# применяется — приговоры исполняются самостоятельно (если условное осуждение не отменено по
# ст. 74 УК РФ); п. 57: отбытое полностью или частично по первому приговору засчитывается.
# Преступление после вынесения первого приговора — совокупность приговоров (ст. 70).
# Сколько отбыто и пересчёт по ст. 72 — на вызывающем; здесь проверяется, что зачёт сделан.

PRIOR_RULE_KEY = "art69.prior_sentence"
PRIOR_NORM = "Преступление до вынесения первого приговора: ч. 5 ст. 69 УК РФ"
PRIOR_SOURCE = (
    "УК РФ ст. 69, ч. 5 — официальная выгрузка http://pravo.gov.ru/proxy/ips/?savertf=&nd="
    "102041891&page=all, получена 27.10.2026, sha256 0243481c50d996a3bddd041854f49077bd34fde1"
    "7734e63735b87e16f4a34d7b; постановление Пленума ВС РФ от 22.12.2015 № 58, пп. 52, 53, 57 "
    "(статус unreviewed, периоды действия сверить в T23)"
)


@dataclass(frozen=True)
class PriorSentenceFacts:
    """Facts of the case; None — not established.

    offence_before_first_sentence — an offence of this case was committed before the first
    sentence was pronounced; first_conditional_in_force — the first sentence is conditional
    (ст. 73) and was not revoked under ст. 74; served_under_first — some punishment was served
    under the first sentence."""

    offence_before_first_sentence: bool | None
    first_conditional_in_force: bool | None
    served_under_first: bool | None


@dataclass(frozen=True)
class DraftPriorSentence:
    """What the draft does; None — not extracted."""

    applies_part5: bool | None
    credits_served: bool | None


def _prior_result(status: CheckStatus, why: str) -> CheckResult:
    return CheckResult(PRIOR_NORM, status, why, PRIOR_SOURCE, NEEDS_LEGAL_REVIEW, PRIOR_RULE_KEY)


_AFTER_FIRST = (
    "Ч. 5 ст. 69 УК РФ применяется к преступлению, совершённому до вынесения первого "
    "приговора; за преступление после его вынесения наказание назначается по совокупности "
    "приговоров (ст. 70 УК РФ)."
)
_CONDITIONAL = (
    "По первому приговору осуждение условное и не отменено: ч. 5 ст. 69 УК РФ не применяется, "
    "приговоры исполняются самостоятельно (п. 53 ППВС № 58)."
)
_NOT_CREDITED = (
    "В окончательное наказание по ч. 5 ст. 69 УК РФ засчитывается наказание, отбытое по "
    "первому приговору, — в проекте зачёт не указан (п. 57 ППВС № 58)."
)


def _grounds_findings(facts: PriorSentenceFacts) -> tuple[list[str], list[str]]:
    """(reasons ч. 5 does not apply, unknown grounds)."""
    reasons: list[str] = []
    unknown: list[str] = []
    if facts.offence_before_first_sentence is False:
        reasons.append(_AFTER_FIRST)
    elif facts.offence_before_first_sentence is None:
        unknown.append("Не установлено, совершено ли преступление до вынесения первого приговора.")
    if facts.first_conditional_in_force is True:
        reasons.append(_CONDITIONAL)
    elif facts.first_conditional_in_force is None:
        unknown.append("Не установлено, является ли осуждение по первому приговору условным.")
    return reasons, unknown


def _credit_finding(
    facts: PriorSentenceFacts, draft: DraftPriorSentence
) -> tuple[str | None, str | None]:
    """(violation, unknown) for the credit of punishment served under the first sentence."""
    if draft.credits_served is True or facts.served_under_first is False:
        return None, None
    if facts.served_under_first is None:
        return None, "Не установлено, отбыто ли наказание по первому приговору."
    if draft.credits_served is None:
        return None, (
            "В проекте не установлено, засчитано ли наказание, отбытое по первому приговору."
        )
    return _NOT_CREDITED, None


def check_prior_sentence(facts: PriorSentenceFacts, draft: DraftPriorSentence) -> CheckResult:
    reasons, unknown = _grounds_findings(facts)
    if draft.applies_part5 is None:
        return _prior_result(
            CheckStatus.INSUFFICIENT_DATA,
            "Не установлено, назначается ли наказание по правилам ч. 5 ст. 69 УК РФ.",
        )
    if draft.applies_part5 is False:
        if reasons:
            return _prior_result(CheckStatus.OK, "Ч. 5 ст. 69 УК РФ не применяется. " + reasons[0])
        if unknown:
            return _prior_result(CheckStatus.INSUFFICIENT_DATA, " ".join(unknown))
        return _prior_result(
            CheckStatus.POSSIBLE_VIOLATION,
            "Преступление совершено до вынесения первого приговора, осуждение по нему не "
            "условное: наказание назначается по правилам ч. 5 ст. 69 УК РФ, а в проекте они "
            "не применены.",
        )
    violation, gap = _credit_finding(facts, draft)
    violations = reasons + ([violation] if violation else [])
    if violations:
        return _prior_result(CheckStatus.POSSIBLE_VIOLATION, " ".join(violations))
    gaps = unknown + ([gap] if gap else [])
    if gaps:
        return _prior_result(CheckStatus.INSUFFICIENT_DATA, " ".join(gaps))
    return _prior_result(
        CheckStatus.OK,
        "Наказание назначено по правилам ч. 5 ст. 69 УК РФ; зачёт отбытого по первому приговору "
        "не нарушен.",
    )
