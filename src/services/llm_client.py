"""LLM access behind a small interface.

- `openai`: any OpenAI-compatible `/chat/completions` endpoint (OpenAI, vLLM, Ollama, proxies),
            with optional fallback to `deepseek_web` if the gateway is unreachable or fails.
- `deepseek_web`: local DeepSeek web-chat proxy (services/deepseek-stateful-wrapper). The proxy
            forwards only the last message and ignores `response_format`, so the system prompt is
            folded into one user turn, every call gets its own conversation (no context bleed
            between cases) and the JSON object is extracted from a possibly fenced answer.
- `fallback`: explicit alias for primary OpenAI client with DeepSeek web proxy fallback.
- `fake`:   fixed sample case for tests. Refused unless LLM_ALLOW_FAKE=true is also set,
            so a server without a model reports an error instead of a sample verdict.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Protocol

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """The model could not be reached or returned something unusable."""


LLM_NOT_CONNECTED = (
    "Языковая модель не подключена — анализ не выполнен. Обратитесь к администратору сервиса."
)


# Transient failures of the model provider (rate limit, overload, gateway errors, network) are
# retried with a growing pause; Retry-After is honoured up to a cap. Other errors fail at once.
LLM_ATTEMPTS = 4
RETRY_PAUSES_SECONDS = (2.0, 4.0, 8.0)
MAX_RETRY_PAUSE_SECONDS = 30.0
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_sleep = asyncio.sleep


def _retry_pause(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        try:
            requested = float(response.headers.get("Retry-After", ""))
        except ValueError:
            requested = None
        if requested is not None and requested >= 0:
            return min(requested, MAX_RETRY_PAUSE_SECONDS)
    return RETRY_PAUSES_SECONDS[min(attempt, len(RETRY_PAUSES_SECONDS) - 1)]


def _final_status_error(status: int) -> LLMError:
    if status == 429:
        return LLMError(
            f"LLM ответил {status}: превышен лимит запросов к языковой модели, "
            "попробуйте через минуту."
        )
    if status in RETRYABLE_STATUSES:
        return LLMError(
            f"LLM ответил {status}: языковая модель временно недоступна, попробуйте позже."
        )
    return LLMError(f"LLM ответил {status}")


class LLMClient(Protocol):
    async def complete_json(self, system: str, user: str) -> dict: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._transport = transport

    async def complete_json(self, system: str, user: str) -> dict:
        api_key = self._api_key if self._api_key is not None else settings.LLM_API_KEY
        if not api_key:
            raise LLMError(
                "Языковая модель не подключена: не задан LLM_API_KEY. Анализ не выполнен."
            )
        api_base = (self._api_base or settings.LLM_API_BASE).rstrip("/")
        model = self._model or settings.LLM_MODEL
        timeout = self._timeout if self._timeout is not None else settings.LLM_TIMEOUT_SECONDS

        user_content = user
        if "json" not in user_content.lower():
            user_content = f"{user_content}\n\nОтветь в формате JSON."

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        url = f"{api_base}/chat/completions"
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            for attempt in range(LLM_ATTEMPTS):
                last = attempt == LLM_ATTEMPTS - 1
                t_req = time.monotonic()
                logger.info(
                    "[LLM] OpenAI request attempt %d/%d: model=%s prompt_chars=%d timeout=%.1fs",
                    attempt + 1,
                    LLM_ATTEMPTS,
                    model,
                    len(user_content) + len(system),
                    timeout,
                )
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except httpx.TransportError as exc:  # connection refused, timeout, reset
                    req_sec = time.monotonic() - t_req
                    logger.warning(
                        "[LLM] Transport error in %.2fs (attempt %d/%d): %s",
                        req_sec,
                        attempt + 1,
                        LLM_ATTEMPTS,
                        exc,
                    )
                    if last:
                        raise LLMError(f"Ошибка обращения к LLM: {type(exc).__name__}") from exc
                    pause = _retry_pause(attempt, None)
                    logger.info("[LLM] Pausing %.1fs before retry...", pause)
                    await _sleep(pause)
                    continue
                req_sec = time.monotonic() - t_req
                status = response.status_code
                if status in RETRYABLE_STATUSES and not last:
                    pause = _retry_pause(attempt, response)
                    logger.info(
                        "[LLM] Retryable status %d in %.2fs (attempt %d/%d). Pausing %.1fs...",
                        status,
                        req_sec,
                        attempt + 1,
                        LLM_ATTEMPTS,
                        pause,
                    )
                    await _sleep(pause)
                    continue
                if status >= 400:
                    logger.warning("LLM API error %d: %s", status, response.text)
                    # Never include request headers in the message: they carry the API key.
                    raise _final_status_error(status)
                logger.info(
                    "[LLM] Succeeded in %.2fs (attempt %d/%d, HTTP %d, bytes=%d)",
                    req_sec,
                    attempt + 1,
                    LLM_ATTEMPTS,
                    status,
                    len(response.content),
                )
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise LLMError(f"Ошибка обращения к LLM: {type(exc).__name__}") from exc
                break

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
    """Adapter for the local DeepSeek web proxy (services/deepseek-stateful-wrapper)."""

    def __init__(
        self,
        api_base: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_base = api_base
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    async def complete_json(self, system: str, user: str) -> dict:
        api_base = self._api_base or settings.LLM_FALLBACK_API_BASE or settings.LLM_API_BASE
        base = api_base.rstrip("/")
        model = self._model or settings.LLM_FALLBACK_MODEL or settings.LLM_MODEL
        if self._api_key is not None:
            api_key = self._api_key
        elif settings.LLM_FALLBACK_API_KEY is not None:
            api_key = settings.LLM_FALLBACK_API_KEY
        else:
            api_key = settings.LLM_API_KEY
        timeout = self._timeout if self._timeout is not None else settings.LLM_TIMEOUT_SECONDS

        conversation_id = f"judgeai-{uuid.uuid4()}"
        prompt = (
            f"{system}\n\nОтветь строго одним JSON-объектом без пояснений и без markdown."
            f"\n\n---\n\n{user}"
        )
        payload = {
            "model": model,
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        t_req = time.monotonic()
        logger.info(
            "[LLM-WEB] DeepSeek web request: base=%s model=%s prompt_chars=%d timeout=%.1fs",
            base,
            model,
            len(prompt),
            timeout,
        )
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            try:
                response = await client.post(
                    f"{base}/chat/completions", json=payload, headers=headers
                )
                req_sec = time.monotonic() - t_req
                logger.info(
                    "[LLM-WEB] DeepSeek web response in %.2fs (HTTP %d, bytes=%d)",
                    req_sec,
                    response.status_code,
                    len(response.content),
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                req_sec = time.monotonic() - t_req
                logger.warning(
                    "[LLM-WEB] HTTP error %d in %.2fs: %s",
                    exc.response.status_code,
                    req_sec,
                    exc.response.text,
                )
                raise LLMError(f"LLM ответил {exc.response.status_code}") from exc
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                req_sec = time.monotonic() - t_req
                logger.warning("[LLM-WEB] Error in %.2fs: %s", req_sec, exc)
                raise LLMError(f"Ошибка обращения к LLM: {type(exc).__name__}") from exc
            finally:
                await self._reset(client, base, conversation_id, headers)

        return extract_json_object(content)

    @staticmethod
    async def _reset(
        client: httpx.AsyncClient, base: str, conversation_id: str, headers: dict
    ) -> None:
        # Best effort: the proxy keeps chats in memory; dropping it frees the slot early.
        try:
            await client.delete(f"{base}/conversations/{conversation_id}", headers=headers)
        except httpx.HTTPError:
            pass


class FallbackLLMClient:
    """Tries the primary LLM client first; on LLMError falls back to the secondary client."""

    def __init__(self, primary: LLMClient, fallback: LLMClient) -> None:
        self.primary = primary
        self.fallback = fallback

    async def complete_json(self, system: str, user: str) -> dict:
        t_start = time.monotonic()
        try:
            return await self.primary.complete_json(system, user)
        except LLMError as primary_exc:
            primary_sec = time.monotonic() - t_start
            logger.warning(
                "Основной LLM провайдер завершился с ошибкой (за %.2fs): %s. "
                "Переключение на фолбэк %s.",
                primary_sec,
                primary_exc,
                type(self.fallback).__name__,
            )
            t_fb = time.monotonic()
            try:
                result = await self.fallback.complete_json(system, user)
                logger.info(
                    "[LLM-FALLBACK] Fallback %s succeeded in %.2fs (total: %.2fs)",
                    type(self.fallback).__name__,
                    time.monotonic() - t_fb,
                    time.monotonic() - t_start,
                )
                return result
            except LLMError as fallback_exc:
                logger.warning(
                    "[LLM-FALLBACK] Fallback %s failed in %.2fs: %s",
                    type(self.fallback).__name__,
                    time.monotonic() - t_fb,
                    fallback_exc,
                )
                raise LLMError(
                    f"Основной LLM шлюз ({primary_exc}) и фолбэк ({fallback_exc}) "
                    "оба вернули ошибку."
                ) from fallback_exc


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
        return DeepSeekWebClient(
            api_base=settings.LLM_API_BASE,
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
        )

    primary = OpenAICompatibleClient(
        api_base=settings.LLM_API_BASE,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
    )
    if settings.LLM_FALLBACK_PROVIDER == "deepseek_web" or settings.LLM_PROVIDER == "fallback":
        fallback = DeepSeekWebClient(
            api_base=settings.LLM_FALLBACK_API_BASE,
            model=settings.LLM_FALLBACK_MODEL,
            api_key=settings.LLM_FALLBACK_API_KEY,
        )
        return FallbackLLMClient(primary=primary, fallback=fallback)
    return primary
