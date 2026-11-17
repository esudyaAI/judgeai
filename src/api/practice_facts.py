"""HTTP (T45.1): factual questions about the shared practice base, counted by code."""

from fastapi import APIRouter, Query

from src.api.deps import CurrentUser, DbSession
from src.application.practice_facts import answer_practice_fact
from src.infrastructure.precedent_store import SqlPrecedentStore
from src.schemas.practice_facts import PracticeFactRead, PracticeFactSourceRead

router = APIRouter()

MAX_QUESTION_LENGTH = 500
HINT = (
    "Вопрос не распознан как вопрос о практике. Укажите одну статью (часть, пункт) и что "
    "посчитать, например: «средний срок по ч. 4 ст. 159»."
)


@router.get("/facts", response_model=PracticeFactRead)
async def practice_fact(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(..., min_length=1, max_length=MAX_QUESTION_LENGTH),
):
    answer = await answer_practice_fact(SqlPrecedentStore(db), q)
    if answer is None:
        return PracticeFactRead(answered=False, hint=HINT)
    facts, comparison = answer.facts, answer.facts.comparison
    return PracticeFactRead(
        answered=True,
        text=answer.text,
        qualification=str(facts.question.qualification),
        found=facts.found,
        counted=len(facts.counted),
        excluded=facts.excluded,
        with_term=comparison.with_term,
        enough_data=facts.enough_data,
        # Below the practice minimum the statistics are not stated (see the domain module).
        mean_months=facts.mean_months if facts.enough_data else None,
        median_months=comparison.median_months if facts.enough_data else None,
        p25_months=comparison.p25_months if facts.enough_data else None,
        p75_months=comparison.p75_months if facts.enough_data else None,
        min_months=comparison.min_months,
        max_months=comparison.max_months,
        conditional_share=comparison.conditional_share,
        sources=[
            PracticeFactSourceRead(
                card_id=c.card_id,
                court_name=c.court_name,
                decision_date=c.decision_date.isoformat() if c.decision_date else None,
                uid=c.uid,
                source_url=c.source_url,
                months=c.months,
                conditional=c.conditional,
            )
            for c in facts.counted
        ],
    )
