"""Reversible local replacements and an explicit external-processing decision."""

import re
from dataclasses import dataclass

_TOKEN = re.compile(r"\[JAI_[a-f0-9]{32}_\d+\]")


class PrivacyRejected(ValueError):
    """A transformation cannot safely preserve the source/response correspondence."""


class ExternalProcessingDenied(RuntimeError):
    """The destination has no recorded external-processing approval."""


@dataclass(frozen=True)
class ExternalProcessingPolicy:
    approval_id: str | None
    endpoints: tuple[str, ...]

    def require(self, endpoint: str) -> None:
        allowed = {value.rstrip("/") for value in self.endpoints if value.strip()}
        if (
            not self.approval_id
            or not self.approval_id.strip()
            or endpoint.rstrip("/") not in allowed
        ):
            raise ExternalProcessingDenied("Внешняя обработка данных не согласована.")


@dataclass(frozen=True)
class IdentifierSpan:
    start: int
    end: int


class PseudonymSession:
    """The replacement table is private process memory; never part of a provider request."""

    def __init__(self, nonce: str):
        if re.fullmatch(r"[a-f0-9]{32}", nonce) is None:
            raise PrivacyRejected("Некорректное пространство замен.")
        self._prefix = f"[JAI_{nonce}_"
        self._tokens: dict[str, str] = {}
        self._originals: dict[str, str] = {}

    def mask(self, text: str, spans: tuple[IdentifierSpan, ...]) -> str:
        if self._prefix in text:
            raise PrivacyRejected("Конфликт пространства замен с исходным текстом.")
        merged: list[tuple[int, int]] = []
        for span in sorted(spans, key=lambda s: (s.start, s.end)):
            if type(span.start) is not int or type(span.end) is not int:
                raise PrivacyRejected("Некорректные координаты идентификатора.")
            if not 0 <= span.start < span.end <= len(text):
                raise PrivacyRejected("Некорректные координаты идентификатора.")
            if merged and span.start < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], span.end))
            else:
                merged.append((span.start, span.end))
        pieces, previous = [], 0
        for start, end in merged:
            original = text[start:end]
            token = self._tokens.get(original)
            if token is None:
                token = f"{self._prefix}{len(self._tokens) + 1}]"
                self._tokens[original] = token
                self._originals[token] = original
            pieces.extend((text[previous:start], token))
            previous = end
        pieces.append(text[previous:])
        return "".join(pieces)

    def restore(self, text: str) -> str:
        def original(match):
            value = self._originals.get(match[0])
            if value is None:
                raise PrivacyRejected("Ответ содержит неизвестную замену.")
            return value

        return _TOKEN.sub(original, text)
