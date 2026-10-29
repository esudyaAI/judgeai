"""Adapter: split a verdict text into its introductory, descriptive and operative parts.

Rule-based, no LLM. Headings may be written with spaced letters ("У С Т А Н О В И Л") and in
any case. Text that cannot be classified is never dropped: without headings the whole text is
the descriptive part, so nothing is lost.
"""

import re
from dataclasses import dataclass

TRIM_MARK = "\n[…]\n"


def _heading(word: str) -> re.Pattern:
    spaced = r"[ \t]*".join(word)
    return re.compile(rf"(?<![а-яё]){spaced}(?:[ \t]*а)?(?![а-яё])[ \t]*:?", re.IGNORECASE)


_ESTABLISHED = _heading("установил")
_SENTENCED = _heading("приговорил")


def _is_heading(match: re.Match) -> bool:
    """The word in running text ("суд установил, что") is not a heading.

    A heading is written in capitals, with spaced letters, or ends with a colon.
    """
    token = match.group(0).strip()
    letters = token.rstrip(":").replace(" ", "").replace("\t", "")
    return token.endswith(":") or letters.isupper() or len(token.rstrip(":").strip()) > len(letters)


def _find_heading(pattern: re.Pattern, text: str, start: int = 0) -> re.Match | None:
    return next((m for m in pattern.finditer(text, start) if _is_heading(m)), None)


@dataclass(frozen=True)
class VerdictSegments:
    introduction: str
    description: str
    operative: str
    recognized: bool

    def model_context(self, limit: int) -> str:
        """Text for a model prompt that never loses the operative part or the introduction.

        The descriptive part is shortened in the middle when the whole does not fit.
        """
        parts = [self.introduction, self.description, self.operative]
        full = "\n\n".join(p for p in parts if p)
        if len(full) <= limit:
            return full
        fixed = "\n\n".join(p for p in (self.introduction, self.operative) if p)
        room = limit - len(fixed) - len(TRIM_MARK) - 4
        if room <= 0:
            head = fixed[: max(0, limit - len(TRIM_MARK))]
            return head + TRIM_MARK[: limit - len(head)]
        half = room // 2
        description = self.description[:half] + TRIM_MARK + self.description[-(room - half) :]
        return "\n\n".join(p for p in (self.introduction, description, self.operative) if p)


def segment_verdict(text: str) -> VerdictSegments:
    established = _find_heading(_ESTABLISHED, text)
    search_from = established.end() if established else 0
    sentenced = _find_heading(_SENTENCED, text, search_from)
    if not established and not sentenced:
        return VerdictSegments("", text, "", recognized=False)
    if established:
        introduction = text[: established.start()].strip()
        description_start = established.end()
    else:
        introduction, description_start = "", 0
    if sentenced:
        description = text[description_start : sentenced.start()].strip()
        operative = text[sentenced.end() :].strip()
    else:
        description, operative = text[description_start:].strip(), ""
    return VerdictSegments(introduction, description, operative, recognized=True)
