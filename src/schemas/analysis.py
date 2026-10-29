"""Structured case analysis — the contract between the backend and the cabinet UI.

Stored in `Message.analysis` (with `schema_version`) and served as `MessageRead.result`.
Field names are snake_case like the rest of the API; the frontend adapter maps them to the
camelCase `CaseAnalysis` in its src/api/types.ts.
"""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

SCHEMA_VERSION = 1


class ApiModel(BaseModel):
    pass


class AnalysisStats(ApiModel):
    documents: int
    pages: int
    seconds: int


class Qualification(ApiModel):
    article: str = Field(description="e.g. 'п. «в» ч. 2 ст. 158 УК РФ'")
    title: str


class Circumstance(ApiModel):
    name: str
    norm: str


class PunishmentVariant(ApiModel):
    label: str
    title: str
    details: str
    rationale: str


class SimilarVerdictRef(ApiModel):
    verdict_id: int | None = None
    punishment: str
    court: str
    match: str
    score: int = Field(ge=0, le=100)


class PrecedentFilterRead(ApiModel):
    name: str
    state: str
    reason: str
    action: str


class PrecedentMatchRead(ApiModel):
    """A comparable precedent from the practice base; its fabula is never returned."""

    card_id: int
    court_name: str | None
    decision_date: str | None
    uid: str | None
    source_url: str | None
    qualifications: list[str]
    punishment_months: int | None
    conditional: bool
    recidivism: str | None
    score: float = Field(ge=0, le=1)
    breakdown: dict[str, dict[str, float]]
    filters: list[PrecedentFilterRead]
    channels: list[str]


class PracticeComparisonRead(ApiModel):
    """Terms imposed in the comparable precedents and the draft's place among them (T28)."""

    qualification: str | None = None
    recidivism: str | None = None
    total: int
    with_term: int
    enough_data: bool
    min_months: int | None
    p25_months: float | None
    median_months: float | None
    p75_months: float | None
    max_months: int | None
    conditional_share: float | None
    art64_share: float | None
    art73_share: float | None
    draft_months: int | None
    draft_percentile: float | None
    position: Literal["below", "within", "above"] | None
    candidates: int
    excluded: int
    vector_used: bool


class SentenceScale(ApiModel):
    """All terms in months; the UI draws them on a 0..sanction_max_months axis."""

    sanction_max_months: int = Field(gt=0)
    limit_months: int | None = None
    limit_norm: str | None = None
    # Interquartile range and median of comparable precedents (T28); the field keeps its
    # historical name, the value is the median.
    practice_months: tuple[int, int] | None = None
    avg_similar_months: int | None = None
    recommended_months: int | None = Field(default=None, ge=0)
    within_sanction: bool | None = None
    extra_notes: list[str] = []


class DraftDocument(ApiModel):
    filename: str
    note: str


class ImposedCountRead(ApiModel):
    qualification: str
    punishment: str
    additional: list[str] = []
    imprisonment_months: int | None = None
    quote: str


class ImposedSentenceRead(ApiModel):
    """Punishment read from the operative part of the uploaded draft (regex, windows via LLM)."""

    counts: list[ImposedCountRead] = []
    final: str | None = None
    aggregation_rule: str | None = None
    conditional: bool = False
    probation_months: int | None = None
    final_quote: str | None = None


class CaseAnalysis(ApiModel):
    legal_checks: list["LegalCheck"] = Field(default_factory=list)
    imposed_sentence: ImposedSentenceRead | None = None
    schema_version: Literal[1] = SCHEMA_VERSION
    stats: AnalysisStats
    prompt: str
    fabula: str
    qualification: Qualification | None = None
    draft: DraftDocument | None = None
    scale: SentenceScale | None = None
    mitigating: list[Circumstance] = []
    aggravating: str | None = None
    personality: str | None = None
    variants: list[PunishmentVariant] = []
    similar: list[SimilarVerdictRef] = []
    # "cards": precedent cards (T24–T27); "text": free-text fallback over the knowledge base;
    # "none": nothing found; None: the knowledge base was not searched.
    precedent_source: Literal["cards", "text", "none"] | None = None
    precedents: list[PrecedentMatchRead] = []
    practice: PracticeComparisonRead | None = None
    practice_episodes: list[PracticeComparisonRead] = Field(default_factory=list)
    # Human-readable caveats the UI must show (e.g. unverified sanction, partial OCR).
    warnings: list[str] = []


class LlmCaseFacts(BaseModel):
    """What the LLM is asked to extract. Legal arithmetic is done in code, not by the model."""

    fabula: str
    legal_facts: "LegalFacts | None" = None
    qualification: Qualification | None = None
    sanction_max_months: int | None = Field(
        default=None, gt=0, description="Max term of imprisonment in the article's sanction, months"
    )
    mitigating: list[Circumstance] = []
    aggravating: list[Circumstance] = []
    personality: str | None = None
    recommended_months: int | None = Field(default=None, ge=0)
    variants: list[PunishmentVariant] = []


class CitedFact(BaseModel):
    value: StrictStr | StrictInt | StrictBool
    quote: str = Field(min_length=6, max_length=2000)


class LegalFacts(BaseModel):
    guilt: CitedFact | None = None
    category: CitedFact | None = None
    sanction_max_months: CitedFact | None = None
    harsher_than_imprisonment: CitedFact | None = None
    real_imprisonment: CitedFact | None = None
    history_complete: CitedFact | None = None
    # Punishment imposed in the operative part of the draft (imprisonment, whole months).
    imposed_imprisonment_months: CitedFact | None = None
    art64_applied: CitedFact | None = None
    # Each dictionary describes ONE distinct prior judgment and cites every supplied field.
    prior_convictions: list[dict[str, CitedFact]] = Field(default_factory=list, max_length=100)


class LegalCheck(BaseModel):
    norm: str
    status: Literal["ok", "possible_violation", "insufficient_data"]
    explanation: str
    source: str
    value: str | None = None
    evidence: list[str] = Field(default_factory=list)
    needs_legal_review: bool = True


# Resolve references declared below the backwards-compatible result classes.
CaseAnalysis.model_rebuild()
LlmCaseFacts.model_rebuild()
