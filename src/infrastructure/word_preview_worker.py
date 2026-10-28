"""Run one conversion per offline container lifetime; no app settings or credentials."""

import os
import resource
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from src.application.upload_validation import ValidateUpload
from src.domain.uploads import DocxLimits, PdfLimits
from src.infrastructure.docx_inspector import DocxInspector
from src.infrastructure.pdf_process import PdfProcessInspector
from src.infrastructure.preview_spool import TOKEN, PreviewSpool, write_status

MAX_BYTES = 50 * 1024 * 1024


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def convert(source: Path, destination: Path) -> None:
    """Only call in the offline, read-only container configured in compose."""
    with source.open("rb") as document:
        ValidateUpload(DocxInspector(), DocxLimits()).execute(document, source.suffix)
    with tempfile.TemporaryDirectory(prefix="word-preview-") as temporary:
        work = Path(temporary)
        incoming = work / ("document" + source.suffix)
        outgoing = work / "output"
        profile = work / "profile"
        outgoing.mkdir()
        profile.mkdir()
        shutil.copyfile(source, incoming)
        (profile / "user").mkdir()
        (profile / "user" / "registrymodifications.xcu").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>'
            "</item></oor:items>"
        )
        # The converter cannot traverse the root-owned shared queue or API uploads.
        for path in [work, *work.rglob("*")]:
            os.chown(path, 65534, 65534)
        command = [
            "/usr/bin/soffice",
            "-env:UserInstallation=" + profile.as_uri(),
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(outgoing),
            str(incoming),
        ]
        process = subprocess.Popen(
            command,
            cwd=work,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            user=65534,
            group=65534,
            extra_groups=[],
            preexec_fn=_limits,
            env={
                "HOME": str(work),
                "TMPDIR": str(work),
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
        )
        try:
            if process.wait(timeout=45) != 0:
                raise ValueError("conversion failed")
        finally:
            # Kill the process group even if the main process has already exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        output = outgoing / "document.pdf"
        # A hostile converter output cannot redirect the privileged parent to another file.
        with os.fdopen(os.open(output, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as pdf:
            info = os.fstat(pdf.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise ValueError("invalid output")
            PdfProcessInspector().inspect(pdf, PdfLimits(max_source_bytes=MAX_BYTES))
            pdf.seek(0)
            with destination.open("xb") as target:
                os.chmod(destination, 0o600)
                shutil.copyfileobj(pdf, target, 1024 * 1024)


def run_one(spool: PreviewSpool) -> bool:
    with spool.locked():
        spool.cleanup()
        jobs = []
        for path in spool.root.iterdir():
            if TOKEN.fullmatch(path.name):
                job = spool._read(path.name)
                if job["status"] == "converting" and time.time() - job.get("started_at", 0) > 90:
                    job.update(
                        status="failed", error="Преобразование прервано. Повторите просмотр."
                    )
                    (path / ("source" + job["suffix"])).unlink(missing_ok=True)
                    write_status(path, job)
                if job["status"] == "queued":
                    jobs.append(job)
        if not jobs:
            return False
        job = min(jobs, key=lambda item: item["created_at"])
        directory = spool.root / job["id"]
        job.update(status="converting", started_at=time.time())
        write_status(directory, job)
    source = directory / ("source" + job["suffix"])
    output = directory / "preview.pdf"
    try:
        convert(source, output)
        job.update(status="ready")
    except Exception:
        output.unlink(missing_ok=True)
        job.update(
            status="failed",
            error="Не удалось преобразовать Word. Скачайте оригинал или загрузите PDF.",
        )
    finally:
        source.unlink(missing_ok=True)
        write_status(directory, job)
    return True


if __name__ == "__main__":
    lifetime = time.monotonic()
    queue = PreviewSpool(Path("/app/previews"))
    while not run_one(queue):
        time.sleep(1)
    # Avoid restart-policy backoff for successful short conversions.
    time.sleep(max(0, 10.1 - (time.monotonic() - lifetime)))
    # The PID namespace is destroyed on exit, including any escaped converter children.
    # Compose restarts a fresh worker for the next job.
