from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from src.api.deps import CurrentUser, DbSession
from src.application.reports import CreateReport
from src.domain.reports import ReportExportFailed, ReportNotFound, ReportUnavailable
from src.infrastructure.report_docx import DocxReportExporter
from src.infrastructure.reports import SqlReportRepository

router = APIRouter()


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    chat_id: int
    source_message_id: int
    version: int
    snapshot_sha256: str
    docx_sha256: str
    created_at: datetime


class ReportDetail(ReportSummary):
    snapshot: dict


def report_error(exc):
    code = (
        404
        if isinstance(exc, ReportNotFound)
        else 503
        if isinstance(exc, ReportExportFailed)
        else 409
    )
    return HTTPException(code, str(exc))


@router.post(
    "/chats/{chat_id}/messages/{message_id}/reports", response_model=ReportSummary, status_code=201
)
async def create_report(
    chat_id: int, message_id: int, db: DbSession, user: CurrentUser, response: Response
):
    try:
        report, created = await CreateReport(SqlReportRepository(db), DocxReportExporter()).execute(
            user.user_id, chat_id, message_id
        )
        await db.commit()
    except (ReportNotFound, ReportUnavailable, ReportExportFailed) as exc:
        await db.rollback()
        raise report_error(exc) from None
    response.status_code = 201 if created else 200
    return ReportSummary.model_validate(report)


@router.get("/reports", response_model=list[ReportSummary])
async def list_reports(
    db: DbSession,
    user: CurrentUser,
    chat_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await SqlReportRepository(db).list(user.user_id, chat_id, limit, offset)


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(report_id: UUID, db: DbSession, user: CurrentUser):
    try:
        return ReportDetail.model_validate(
            await SqlReportRepository(db).get(user.user_id, report_id)
        )
    except (ReportNotFound, ReportUnavailable) as exc:
        raise report_error(exc) from None


@router.get("/reports/{report_id}/docx")
async def download_report(report_id: UUID, db: DbSession, user: CurrentUser):
    try:
        report = await SqlReportRepository(db).get(user.user_id, report_id)
    except (ReportNotFound, ReportUnavailable) as exc:
        raise report_error(exc) from None
    return Response(
        report.docx_data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="judgeai-report-v{report.version}.docx"',
            "Cache-Control": "private, no-store",
        },
    )
