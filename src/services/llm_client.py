"""LLM access behind a small interface.

- `openai`: any OpenAI-compatible `/chat/completions` endpoint (OpenAI, vLLM, Ollama, proxies).
- `deepseek_web`: local DeepSeek web-chat proxy (deepseek-stateful-wrapper). The proxy forwards
            only the last message and ignores `response_format`, so the system prompt is folded
            into one user turn, every call gets its own conversation (no context bleed between
            cases) and the JSON object is extracted from a possibly fenced answer.
- `fake`:   fixed sample case for tests. Refused unless LLM_ALLOW_FAKE=true is also set,
            so a server without a model reports an error instead of a sample verdict.
"""

import json
import uuid
from typing import Protocol

import httpx

from src.config import settings


class LLMError(RuntimeError):
    """The model could not be reached or returned something unusable."""


LLM_NOT_CONNECTED = (
    "Языковая модель не подключена — анализ не выполнен. Обратитесь к администратору сервиса."
)


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> dict: ...


class OpenAICompatibleClient:
    async def complete_json(self, system: str, user: str) -> dict:
        if not settings.LLM_API_KEY:
            raise LLMError(
                "Языковая модель не подключена: не задан LLM_API_KEY. Анализ не выполнен."
            )

        payload = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}

        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{settings.LLM_API_BASE.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            # Never include request headers in the message: they carry the API key.
            raise LLMError(f"LLM ответил {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Ошибка обращения к LLM: {type(exc).__name__}") from exc

        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError("LLM вернул не JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("LLM вернул JSON не в виде объекта")
        return data


def extract_json_object(text: str) -> dict:
    """Return the first JSON object in `text`; tolerate markdown fences and prose around it."""
    if not isinstance(text, str):
        raise LLMError("LLM вернул не JSON")
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            data, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(data, dict):
            return data
        start = text.find("{", start + 1)
    raise LLMError("LLM вернул не JSON")


class DeepSeekWebClient:
    """Adapter for the local DeepSeek web proxy. Local development only (see module docstring)."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def complete_json(self, system: str, user: str) -> dict:
        base = settings.LLM_API_BASE.rstrip("/")
        conversation_id = f"judgeai-{uuid.uuid4()}"
        prompt = (
            f"{system}\n\nОтветь строго одним JSON-объектом без пояснений и без markdown."
            f"\n\n---\n\n{user}"
        )
        payload = {
            "model": settings.LLM_MODEL,
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {}
        if settings.LLM_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

        async with httpx.AsyncClient(
            timeout=settings.LLM_TIMEOUT_SECONDS, transport=self._transport
        ) as client:
            try:
                response = await client.post(
                    f"{base}/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                raise LLMError(f"LLM ответил {exc.response.status_code}") from exc
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMError(f"Ошибка обращения к LLM: {type(exc).__name__}") from exc
            finally:
                await self._reset(client, base, conversation_id, headers)

        return extract_json_object(content)

    @staticmethod
    async def _reset(client: httpx.AsyncClient, base: str, conversation_id: str, headers) -> None:
        # Best effort: the proxy keeps chats in memory; dropping it frees the slot early.
        try:
            await client.delete(f"{base}/conversations/{conversation_id}", headers=headers)
        except httpx.HTTPError:
            pass


class FakeLLMClient:
    """Returns the design's sample case regardless of input. Development and tests only."""

    async def complete_json(self, system: str, user: str) -> dict:
        return {
            "fabula": (
                "Подсудимый тайно похитил ноутбук стоимостью 64 000 ₽ из квартиры потерпевшей. "
                "С учётом её дохода ущерб значительный. Похищенное возвращено, ущерб возмещён "
                "полностью (т. 1 л. д. 87)."
            ),
            "qualification": {
                "article": "п. «в» ч. 2 ст. 158 УК РФ",
                "title": "Кража с причинением значительного ущерба гражданину. Средней тяжести.",
            },
            "sanction_max_months": 60,
            "mitigating": [
                {"name": "Явка с повинной", "norm": "п. «и» ч. 1 ст. 61"},
                {"name": "Возмещение ущерба", "norm": "п. «к» ч. 1 ст. 61"},
                {"name": "Признание вины", "norm": "ч. 2 ст. 61"},
            ],
            "aggravating": [],
            "personality": "Ранее не судим, характеризуется положительно, трудоустроен.",
            "recommended_months": 18,
            "variants": [
                {
                    "label": "Основной",
                    "title": "Лишение свободы 1 год 6 месяцев условно",
                    "details": "Испытательный срок 2 года.",
                    "rationale": "Учтены п. «и», «к» ч. 1 ст. 61, отягчающих обстоятельств нет.",
                },
                {
                    "label": "Штраф",
                    "title": "Штраф 100 000 ₽",
                    "details": "В пределах санкции.",
                    "rationale": "С учётом полного возмещения ущерба (ч. 3 ст. 46 УК РФ).",
                },
            ],
        }


def get_llm_client() -> LLMClient:
    if settings.LLM_PROVIDER == "fake":
        if not settings.LLM_ALLOW_FAKE:
            raise LLMError(LLM_NOT_CONNECTED)
        return FakeLLMClient()
    if settings.LLM_PROVIDER == "deepseek_web":
        return DeepSeekWebClient()
    return OpenAICompatibleClient()
