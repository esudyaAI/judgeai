"""HTTP (T45.3): «what does the law provide for this qualification», read from the law base."""

from dataclasses import asdict

from fastapi import APIRouter, Query

from src.api.deps import CurrentUser, DbSession
from src.application.sanction_facts import answer_sanction_fact
from src.infrastructure.sanction_readings import SqlSanctionReadings
from src.schemas.sanction_facts import (
    SanctionFactItemRead,
    SanctionFactRead,
    SanctionFactSourceRead,
)

router = APIRouter()

MAX_QUESTION_LENGTH = 500
HINT = (
    "Вопрос не распознан как вопрос о санкции. Укажите одну статью (часть) и спросите о "
    "наказании по закону, например: «какая санкция по ч. 2 ст. 158»."
)


@router.get("/facts", response_model=SanctionFactRead)
async def sanction_fact(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=MAX_QUESTION_LENGTH),
):
    answer = await answer_sanction_fact(SqlSanctionReadings(db), q)
    if answer is None:
        return SanctionFactRead(answered=False, hint=HINT)
    facts = answer.facts
    source = facts.source
    return SanctionFactRead(
        answered=True,
        text="\n\n".join(t for t in (answer.text, answer.date_note, answer.source) if t),
        qualification=str(facts.question.qualification),
        parsed=bool(facts.sanctions),
        conflict=facts.conflict,
        sanctions=[
            SanctionFactItemRead(
                part=s.part,
                kind=s.kind.value,
                role=s.role.value,
                min_value=s.min_value,
                max_value=s.max_value,
                unit=s.unit.value if s.unit else None,
            )
            for s in facts.sanctions
            if facts.in_force is not False  # T45.9: not in force on the date — not given
        ],
        source=SanctionFactSourceRead(**asdict(source)) if source and facts.sanctions else None,
        on=facts.on,
        in_force_on=facts.in_force,
    )
