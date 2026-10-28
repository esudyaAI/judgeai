"""Модели данных судебных актов Верховного Суда РФ."""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

INSTANCE_LABELS: dict[str, str] = {
    "FIRST": "Первая инстанция",
    "APPEAL": "Апелляция",
    "CASSATION_NOT_INTO_FORCE": "Кассация на не вступившее в силу судебное решение",
    "CASSATION_INTO_FORCE": "Кассация на вступившее в силу судебное решение",
    "SUPERVISORY": "Надзор",
}

PERSON_STATUS_LABELS: dict[str, str] = {
    "PERSON_IN_CASE": "Лицо в деле",
    "VICTIM": "Потерпевший",
    "DEFENDANT": "Обвиняемый/осуждённый",
    "CLAIMER": "Заявитель",
    "PROSECUTOR": "Прокурор",
    "COUNSEL": "Защитник",
}


@dataclass(slots=True)
class ActRef:
    """Ссылка на судебный акт (первая инстанция или итоговый акт ВС РФ)."""

    act_type_name: str | None = None
    court_name: str | None = None
    full_case_number: str | None = None
    first_instance_num: str | None = None
    judge_name: str | None = None
    create_date: str | None = None
    download_link: str | None = None
    judgement_type_name: str | None = None
    reporter_name: str | None = None
    requisition_available: bool | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any] | None) -> ActRef:
        if not payload:
            return cls()
        return cls(
            act_type_name=payload.get("actTypeName"),
            court_name=payload.get("courtName"),
            full_case_number=payload.get("fullCaseNumber"),
            first_instance_num=payload.get("firstInstanceNum"),
            judge_name=payload.get("judgeName"),
            create_date=payload.get("createDate"),
            download_link=payload.get("downloadLink"),
            judgement_type_name=payload.get("judgementTypeName"),
            reporter_name=payload.get("reporterName"),
            requisition_available=payload.get("requisitionAvailable"),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Person:
    short_name: str | None = None
    article: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PersonalityGroup:
    status: str = ""
    status_label: str = ""
    persons: list[Person] = field(default_factory=list)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> PersonalityGroup:
        status = payload.get("status") or ""
        persons = [
            Person(short_name=p.get("shortName"), article=p.get("article"))
            for p in payload.get("personalities") or []
        ]
        return cls(
            status=status,
            status_label=PERSON_STATUS_LABELS.get(status, status),
            persons=persons,
        )


@dataclass(slots=True)
class CaseEvent:
    event_datetime: str | None = None
    type_name: str | None = None
    hearing: bool = False

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> CaseEvent:
        return cls(
            event_datetime=payload.get("eventDateTime"),
            type_name=payload.get("eventTypeName"),
            hearing=bool(payload.get("hearing")),
        )


@dataclass(slots=True)
class ActListItem:
    """Карточка дела из листинга acts.json."""

    claim_id: str
    case_number: str | None = None
    act_type: str | None = None
    act_date: str | None = None
    pdf_id: str | None = None
    proceeding: str | None = None
    instance_code: str | None = None
    instance_label: str | None = None
    collegium: str | None = None
    reporter: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClaimDetails:
    """Детальная карточка производства из claims/{id}.json."""

    claim_id: str
    claim_type: str | None = None
    register_date: str | None = None
    case_type: str | None = None
    sdd_id: str | None = None
    unique_number: str | None = None
    instance: str | None = None
    instance_label: str | None = None
    incoming_method: str | None = None
    department: str | None = None
    first_act: ActRef = field(default_factory=ActRef)
    final_act: ActRef = field(default_factory=ActRef)
    personalities: list[PersonalityGroup] = field(default_factory=list)
    events: list[CaseEvent] = field(default_factory=list)

    @classmethod
    def from_api(cls, claim_id: str, payload: dict[str, Any]) -> ClaimDetails:
        instance = payload.get("instance")
        return cls(
            claim_id=claim_id,
            claim_type=payload.get("claimType"),
            register_date=payload.get("registerDate"),
            case_type=payload.get("caseType"),
            sdd_id=payload.get("sddId"),
            unique_number=payload.get("uniqueNumber"),
            instance=instance,
            instance_label=INSTANCE_LABELS.get(instance or "", instance),
            incoming_method=payload.get("incomingMethodName"),
            department=payload.get("departmentName"),
            first_act=ActRef.from_api(payload.get("firstAct")),
            final_act=ActRef.from_api(payload.get("finalAct")),
            personalities=[
                PersonalityGroup.from_api(g) for g in payload.get("personalities") or []
            ],
            events=[CaseEvent.from_api(e) for e in payload.get("events") or []],
        )

    def all_articles(self) -> list[str]:
        seen: list[str] = []
        for group in self.personalities:
            for person in group.persons:
                for chunk in (person.article or "").split(";"):
                    chunk = chunk.strip()
                    if chunk and chunk not in seen:
                        seen.append(chunk)
        return seen

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "case_number": self.sdd_id,
            "sdd_id": self.sdd_id,
            "unique_number": self.unique_number,
            "case_type": self.case_type,
            "register_date": self.register_date,
            "instance": self.instance,
            "instance_label": self.instance_label,
            "incoming_method": self.incoming_method,
            "department": self.department,
            "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
        for prefix, ref in (("first", self.first_act), ("final", self.final_act)):
            record[f"{prefix}_act_type"] = ref.act_type_name
            record[f"{prefix}_court"] = ref.court_name
            record[f"{prefix}_case_number"] = ref.full_case_number
            record[f"{prefix}_first_instance_num"] = ref.first_instance_num
            record[f"{prefix}_judge"] = ref.judge_name
            record[f"{prefix}_date"] = ref.create_date
            record[f"{prefix}_judgement"] = ref.judgement_type_name
            record[f"{prefix}_reporter"] = ref.reporter_name
        record["pdf_id"] = self.final_act.download_link.rsplit("/", 1)[-1] if self.final_act.download_link else None
        record["pdf_url"] = (
            f"https://www.vsrf.ru{self.final_act.download_link}"
            if self.final_act.download_link
            else None
        )
        record["articles"] = self.all_articles()
        record["personalities"] = [asdict(g) for g in self.personalities]
        record["events"] = [asdict(e) for e in self.events]
        return record


@dataclass(slots=True)
class ParsedActText:
    """Результат структурного разбора текста судебного акта."""

    source_path: str | None = None
    act_kind: str | None = None
    case_number: str | None = None
    act_date: str | None = None
    city: str | None = None
    collegium: str | None = None
    presiding_judge: str | None = None
    judges: list[str] = field(default_factory=list)
    secretary: str | None = None
    prosecutor: str | None = None
    convicted: list[str] = field(default_factory=list)
    lower_court: str | None = None
    lower_court_date: str | None = None
    articles: list[str] = field(default_factory=list)
    outcome: str | None = None
    outcome_verbs: list[str] = field(default_factory=list)
    operative_part: str | None = None
    sentence: str | None = None
    text_length: int = 0

    def to_record(self) -> dict[str, Any]:
        return asdict(self)
