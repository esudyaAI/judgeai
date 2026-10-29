"""Private bounded filesystem queue shared only by API and an offline worker."""

import asyncio
import fcntl
import json
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from src.application.document_preview import PreviewNotFound, PreviewUnavailable

TOKEN = re.compile(r"[a-f0-9]{32}\Z")


def write_status(directory: Path, job: dict) -> None:
    temporary = directory / "status.tmp"
    with temporary.open("w") as output:
        os.chmod(temporary, 0o600)
        json.dump(job, output)
    temporary.replace(directory / "status.json")


class PreviewSpool:
    def __init__(self, root: Path, *, ttl: int = 600, capacity: int = 8):
        self.root = root
        self.ttl = ttl
        self.capacity = capacity

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        with (self.root / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def cleanup(self, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for directory in self.root.iterdir():
            if (
                TOKEN.fullmatch(directory.name)
                and directory.is_dir()
                and not directory.is_symlink()
            ):
                try:
                    job = self._read(directory.name, allow_expired=True)
                    if now - job["created_at"] > self.ttl:
                        shutil.rmtree(directory)
                except (PreviewNotFound, OSError, KeyError, TypeError):
                    continue

    def create(self, source: Path, filename: str, owner: int, attachment: tuple | None) -> dict:
        if source.suffix.lower() not in {".docx", ".dotx"}:
            raise PreviewUnavailable("Формат просмотра не поддерживается")
        with self.locked():
            self.cleanup()
            jobs = [p for p in self.root.iterdir() if TOKEN.fullmatch(p.name)]
            # Reopening an existing attachment reuses its short-lived conversion.
            for path in jobs:
                existing = self._read(path.name)
                if (
                    attachment
                    and existing["owner"] == owner
                    and existing["attachment"] == list(attachment)
                ):
                    if existing["status"] != "failed":
                        return existing
            metadata = [self._read(path.name) for path in jobs]
            active = [job for job in metadata if job["status"] in {"queued", "converting"}]
            if len(active) >= self.capacity or sum(job["owner"] == owner for job in active) >= 2:
                raise PreviewUnavailable("Сервис просмотра занят. Попробуйте чуть позже.")
            finished = sorted(
                (job for job in metadata if job not in active), key=lambda item: item["created_at"]
            )
            if len(jobs) >= 32 and finished:
                shutil.rmtree(self.root / finished[0]["id"])
            token = uuid.uuid4().hex
            directory = self.root / token
            directory.mkdir(mode=0o700)
            job = dict(
                id=token,
                owner=owner,
                attachment=attachment,
                filename=filename[:512],
                created_at=time.time(),
                status="queued",
                error=None,
                suffix=source.suffix.lower(),
            )
            try:
                target = directory / ("source" + job["suffix"])
                with source.open("rb") as incoming, target.open("xb") as outgoing:
                    os.chmod(target, 0o600)
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                write_status(directory, job)
            except BaseException:
                shutil.rmtree(directory)
                raise
            return job

    def _read(self, token: str, *, allow_expired: bool = False) -> dict:
        if not TOKEN.fullmatch(token):
            raise PreviewNotFound
        directory = self.root / token
        path = directory / "status.json"
        if directory.is_symlink() or path.is_symlink():
            raise PreviewNotFound
        try:
            with path.open() as source:
                job = json.loads(source.read(8193))
            if job["id"] != token or (
                not allow_expired and time.time() - job["created_at"] > self.ttl
            ):
                raise PreviewNotFound
            return job
        except (OSError, ValueError, KeyError, TypeError):
            raise PreviewNotFound from None

    def get(self, token: str, owner: int) -> dict:
        job = self._read(token)
        if job["owner"] != owner:
            raise PreviewNotFound
        return job

    def pdf(self, token: str, owner: int) -> Path:
        job = self.get(token, owner)
        path = self.root / token / "preview.pdf"
        if job["status"] != "ready" or path.is_symlink() or not path.is_file():
            raise PreviewNotFound
        return path


class AsyncPreviewJobs:
    """Adapt blocking spool I/O to the application port outside the HTTP event loop."""

    def __init__(self, spool: PreviewSpool):
        self.spool = spool

    async def create(
        self, source: str, filename: str, owner: int, attachment: tuple | None
    ) -> dict:
        return await asyncio.to_thread(self.spool.create, Path(source), filename, owner, attachment)

    def get(self, token: str, owner: int) -> dict:
        return self.spool.get(token, owner)

    def pdf(self, token: str, owner: int) -> str:
        return str(self.spool.pdf(token, owner))
