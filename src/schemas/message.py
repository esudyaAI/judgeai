import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationError, computed_field, model_validator

from src.domain.analysis_version import ANALYSIS_VERSION
from src.schemas.analysis import CaseAnalysis

logger = logging.getLogger(__name__)


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str | None
    size: int
    page_count: int | None = None
    extraction_status: str = "ok"


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str | None
    status: str
    stage: str | None = None
    # Raw JSON as stored (kept for backward compatibility with pre-0.4 clients).
    analysis: dict | None
    # True when the stored analysis was computed by another engine version.
    stale: bool | None = None
    error: str | None
    created_at: datetime
    updated_at: datetime | None = None
    attachments: list[AttachmentRead]

    @model_validator(mode="after")
    def _stale_analysis(self) -> "MessageRead":
        """A saved analysis computed by another engine version is stale (T43).

        Analyses saved before the field existed have no ``engine_version`` and
        are stale as well; only completed assistant analyses are considered.
        """
        self.stale = (
            self.role == "assistant"
            and self.status == "completed"
            and self.analysis is not None
            and self.analysis.get("engine_version") != ANALYSIS_VERSION
        )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def result(self) -> CaseAnalysis | None:
        """Typed analysis; None for legacy (pre-0.4) analyses and for unreadable data."""
        if not self.analysis or "schema_version" not in self.analysis:
            return None
        try:
            return CaseAnalysis.model_validate(self.analysis)
        except ValidationError:
            logger.warning("message %s has an analysis that no longer matches the schema", self.id)
            return None


class MessageSendResponse(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead
