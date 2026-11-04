"""Task-local observation of successful provider calls; never stores prompt contents."""

from contextlib import contextmanager
from contextvars import ContextVar

_current: ContextVar[list[dict] | None] = ContextVar("llm_receipts", default=None)


@contextmanager
def capture_receipts():
    receipts: list[dict] = []
    token = _current.set(receipts)
    try:
        yield receipts
    finally:
        _current.reset(token)


def record_receipt(receipt: dict) -> None:
    collector = _current.get()
    if collector is not None:
        collector.append(dict(receipt))
