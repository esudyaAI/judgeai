"""Read an upload digest without exposing paths or following links outside private storage."""

import asyncio
from hashlib import sha256
from pathlib import Path

from src.config import settings


def _digest(stored_path: str) -> str | None:
    try:
        path = Path(stored_path)
        root = Path(settings.UPLOAD_DIR).resolve()
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(root) or resolved == root:
            return None
        digest, size = sha256(), 0
        with resolved.open("rb") as source:
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > settings.UPLOAD_MAX_MB * 1024 * 1024:
                    return None
                digest.update(block)
        return digest.hexdigest()
    except (OSError, ValueError):
        return None


async def upload_digest(stored_path: str) -> str | None:
    return await asyncio.to_thread(_digest, stored_path)
