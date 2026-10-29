# Domain Layer — ст. 86 «Судимость» и ст. 95 «Сроки погашения судимости» УК РФ.
# ч. 1: судимость — со дня вступления приговора в законную силу до погашения или снятия;
# ч. 2: освобождённый от наказания считается несудимым; ч. 3: сроки погашения —
#   а) условно осуждённые — по истечении испытательного срока;
#   б) более мягкие виды, чем лишение свободы, — один год после отбытия или исполнения;
#   в) лишение свободы за небольшой/средней тяжести — три года после отбытия;
#   г) лишение свободы за тяжкие — восемь лет (ред. ФЗ от 23.07.2013 N 218-ФЗ; ранее шесть);
#   д) за особо тяжкие — десять лет (ред. N 218-ФЗ; ранее восемь);
# ч. 4: при досрочном освобождении — от фактического освобождения от основного и
# дополнительного наказаний; ч. 3.1 и ч. 5: снятие судимости (дата передаётся вызывающим).
# ст. 95 (ред. ФЗ от 05.04.2010 N 48-ФЗ): за преступления до 18 лет — 6 месяцев, 1 год, 3 года.
# Пленум ВС РФ от 07.06.2022 N 14: п. 4 — отменённое условное осуждение считается по пп. «б»–«д»
# (вызывающий передаёт IMPRISONMENT); п. 5 — принудительные работы — п. «б», за особо тяжкие
# всегда п. «д»; п. 8 — закон на момент преступления с учётом ст. 10 (поэтому преступления до
# 03.08.2013 — прежние 6 и 8 лет); п. 10 — срок течёт со следующего дня после отбытия;
# п. 11 — при УДО не ранее окончания неотбытой части; п. 12 — после отбытия и дополнительного
# наказания (вызывающий передаёт в served_on более позднюю дату).
# The last day of a term (served_on + N) is a boundary courts treat differently, so it yields
# None ("cannot decide"), like same-day events in criminal_record.
# TODO(T4/T23): категория неосторожных тяжких до ФЗ от 17.06.2019 N 146-ФЗ (ППВС № 14 п. 8),
# длящиеся преступления несовершеннолетних (п. 7), ч. 3.1 как отдельное основание, приостановление
# при уклонении (п. 12) — решает вызывающий/судья; дата вступления N 218-ФЗ в силу (03.08.2013)
# взята из вторичных источников.
import calendar
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from legal_core.entities import Category

NEEDS_LEGAL_REVIEW = True

# Day ФЗ от 23.07.2013 N 218-ФЗ (8 and 10 years) took effect; earlier offences keep 6 and 8 years.
TERMS_RAISED_ON = date(2013, 8, 3)

SOURCE = (
    "УК РФ ст. 86, ст. 95 — официальная выгрузка "
    "http://pravo.gov.ru/proxy/ips/?savertf=&nd=102041891&page=all, получена 27.10.2026, "
    "sha256 0243481c50d996a3bddd041854f49077bd34fde17734e63735b87e16f4a34d7b (статус "
    "unreviewed, периоды действия сверить в T23); прежние сроки пп. «г», «д» до ФЗ от "
    "23.07.2013 N 218-ФЗ и дата его вступления в силу — вторичные публикации; Пленум ВС РФ от "
    "07.06.2022 N 14, пп. 4, 5, 7, 8, 10–12 — https://vsrf.ru/documents/own/31227/ (изложение)"
)


class Disposition(StrEnum):
    """How the prior sentence was carried out, as it matters for ч. 3 ст. 86."""

    CONDITIONAL = "conditional"  # ст. 73, not revoked
    NON_CUSTODIAL = "non_custodial"  # milder than imprisonment, incl. forced labour
    IMPRISONMENT = "imprisonment"  # real imprisonment, incl. revoked conditional sentence


@dataclass(frozen=True)
class SentenceForExpungement:
    """Facts of one prior sentence. ``None`` means the fact is unknown.

    ``served_on`` — the day the main and every additional punishment were served or executed,
    or the day of actual early release (ч. 4 ст. 86). ``unserved_until`` — on early release, the
    day the unserved part would have ended. ``probation_months`` — probation including
    extensions (ч. 2 ст. 74), counted from legal force (ч. 3 ст. 73). ``removed_on`` — the day
    the record was removed (ч. 3.1, ч. 5 ст. 86).
    """

    category: Category
    disposition: Disposition
    offence_date: date | None
    minor_at_offence: bool | None
    legal_force_date: date | None
    served_on: date | None = None
    probation_months: int | None = None
    unserved_until: date | None = None
    released_from_punishment: bool = False
    removed_on: date | None = None

    def __post_init__(self) -> None:
        conditional = self.disposition is Disposition.CONDITIONAL
        if self.probation_months is not None and (not conditional or self.probation_months <= 0):
            raise ValueError("probation_months must be positive and only for a conditional one")
        if self.unserved_until is not None and conditional:
            raise ValueError("unserved_until applies to early release, not to probation")


@dataclass(frozen=True)
class Expungement:
    """``last_day`` — the last day the record exists by ч. 3 ст. 86; None — cannot compute."""

    last_day: date | None
    basis: str
    needs_legal_review: bool = NEEDS_LEGAL_REVIEW


def add_months(day: date, months: int) -> date:
    """Corresponding date ``months`` later; a missing day becomes the month's last day."""
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _term(s: SentenceForExpungement) -> tuple[int | None, str]:
    """Months of the term of ч. 3 ст. 86 / ст. 95 and its basis; None — cannot choose."""
    especially = s.category is Category.ESPECIALLY_GRAVE
    custodial = s.disposition is Disposition.IMPRISONMENT
    if s.minor_at_offence is None:
        return None, "Не установлено, совершено ли преступление несовершеннолетним (ст. 95 УК РФ)."
    if s.minor_at_offence:
        if not custodial and especially:
            return None, (
                "Особо тяжкое преступление несовершеннолетнего без лишения свободы: выбор между "
                "п. «а» и п. «в» ст. 95 УК РФ требует оценки судьи."
            )
        if not custodial:
            return 6, "п. «а» ст. 95 УК РФ — шесть месяцев"
        if s.category <= Category.MEDIUM:
            return 12, "п. «б» ст. 95 УК РФ — один год"
        return 36, "п. «в» ст. 95 УК РФ — три года"
    if not custodial and not especially:
        return 12, "п. «б» ч. 3 ст. 86 УК РФ — один год"
    if s.category <= Category.MEDIUM:
        return 36, "п. «в» ч. 3 ст. 86 УК РФ — три года"
    point, new, old = ("«д»", 10, 8) if especially else ("«г»", 8, 6)
    if s.offence_date is None:
        return (
            None,
            f"Не установлена дата преступления: срок п. {point} ч. 3 ст. 86 УК РФ "
            "зависит от редакции (ФЗ от 23.07.2013 N 218-ФЗ).",
        )
    if s.offence_date < TERMS_RAISED_ON:
        return 12 * old, (
            f"п. {point} ч. 3 ст. 86 УК РФ в ред. до ФЗ от 23.07.2013 N 218-ФЗ — {old} лет "
            "(преступление до 03.08.2013, ухудшающий закон обратной силы не имеет, ст. 10 УК РФ)"
        )
    return 12 * new, f"п. {point} ч. 3 ст. 86 УК РФ — {new} лет"


def expungement(s: SentenceForExpungement) -> Expungement:
    """Candidate last day of the record by ч. 3 ст. 86 (removal by court is not applied)."""
    if s.released_from_punishment:
        return Expungement(None, "ч. 2 ст. 86 УК РФ: освобождённый от наказания несудим.")
    if s.disposition is Disposition.CONDITIONAL:
        if s.legal_force_date is None or s.probation_months is None:
            return Expungement(
                None, "Не установлены дата вступления приговора в силу или испытательный срок."
            )
        return Expungement(
            add_months(s.legal_force_date, s.probation_months),
            "п. «а» ч. 3 ст. 86 УК РФ — по истечении испытательного срока (ч. 3 ст. 73 УК РФ)",
        )
    months, basis = _term(s)
    if months is None:
        return Expungement(None, basis)
    if s.served_on is None:
        return Expungement(None, f"{basis}; не установлена дата отбытия наказания.")
    last_day = add_months(s.served_on, months)
    if s.unserved_until is not None and s.unserved_until > last_day:
        return Expungement(
            s.unserved_until,
            f"{basis}; неотбытая часть при досрочном освобождении длиннее — до её окончания "
            "(ППВС РФ N 14, п. 11)",
        )
    return Expungement(last_day, basis)


def record_active_on(s: SentenceForExpungement, day: date) -> bool | None:
    """Whether the person has this record on ``day``; None — cannot decide from the facts."""
    if s.released_from_punishment:
        return False
    if s.removed_on is not None and day >= s.removed_on:
        return None if day == s.removed_on else False
    if s.legal_force_date is None:
        return None
    if day <= s.legal_force_date:
        return None if day == s.legal_force_date else False
    last_day = expungement(s).last_day
    if last_day is None or day == last_day:
        return None
    return day < last_day
