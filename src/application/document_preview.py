"""Owner-bound document access through storage and conversion ports."""

from dataclasses import dataclass
from typing import Protocol


class PreviewNotFound(Exception):
    pass


class PreviewUnavailable(Exception):
    pass


@dataclass(frozen=True)
class AttachmentSource:
    path: str
    suffix: str
    filename: str


class AttachmentRepository(Protocol):
    async def get(self, owner: int, chat: int, attachment: int) -> AttachmentSource: ...


class PreviewJobs(Protocol):
    async def create(
        self, source: str, filename: str, owner: int, attachment: tuple | None
    ) -> dict: ...
    def get(self, token: str, owner: int) -> dict: ...
    def pdf(self, token: str, owner: int) -> str: ...


class DocumentPreview:
    def __init__(self, attachments: AttachmentRepository, jobs: PreviewJobs):
        self.attachments = attachments
        self.jobs = jobs

    async def prepare(self, owner: int, chat: int, attachment: int) -> dict:
        source = await self.attachments.get(owner, chat, attachment)
        if source.suffix.lower() not in {".docx", ".dotx"}:
            raise PreviewUnavailable("Преобразование требуется только для документов Word")
        return await self.jobs.create(source.path, source.filename, owner, (chat, attachment))

    async def status(self, owner: int, token: str) -> dict:
        job = self.jobs.get(token, owner)
        if job["attachment"] is not None:
            await self.attachments.get(owner, *job["attachment"])
        return job

    async def pdf(self, owner: int, token: str) -> str:
        await self.status(owner, token)
        return self.jobs.pdf(token, owner)
