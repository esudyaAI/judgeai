"""Adapter (T45.2): a language model rewords a practice answer counted by code.

The model receives only the qualification and the answer written by code — public figures
of the practice base, no case documents and no user files. It is asked not to add, round or
recompute numbers; the use case checks that it did not. A model error is not an error of the
answer: the code's own wording is shown instead.
"""

import logging

from src.services.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

SYSTEM = (
    "Ты помощник судьи. Тебе дают ответ о судебной практике, посчитанный программой. "
    "Перескажи его ясно и коротко по-русски для судьи. Нельзя добавлять, округлять, "
    "пересчитывать или переводить в другие единицы числа: используй только числа из ответа "
    "программы и в той же записи. Не добавляй сведений, которых нет в ответе, не давай "
    'советов о наказании. Верни JSON {"answer": "<текст>"}.'
)


class LlmAnswerPhraser:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def phrase(self, qualification: str, facts_text: str) -> str | None:
        user = f"Квалификация: {qualification}\nОтвет программы: {facts_text}\nВерни JSON."
        try:
            data = await self._llm.complete_json(SYSTEM, user)
        except LLMError as exc:
            # Only the type and status: the model's message may echo the input.
            logger.warning(
                "[PRACTICE-FACTS] wording by model failed: %s (status=%s)",
                type(exc).__name__,
                getattr(exc, "status", None),
            )
            return None
        answer = data.get("answer") if isinstance(data, dict) else None
        return answer if isinstance(answer, str) else None
