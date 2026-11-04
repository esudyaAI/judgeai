"""Guarded application clients; low-level provider transports remain independently testable."""

import re
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit

from src.application.anonymization import anonymize_texts, expand_source_fragment, identifier_spans
from src.config import settings
from src.domain.privacy import ExternalProcessingPolicy, PrivacyRejected, PseudonymSession
from src.infrastructure.identifier_detector import detect_identifiers
from src.services.llm_receipts import record_receipt
from src.services.provider_errors import EmbeddingError, LLMError, ProcessingNotApproved

EMBEDDING_PRIVACY_VERSION = "privacy-redaction/1"


def processing_policy() -> ExternalProcessingPolicy:
    return ExternalProcessingPolicy(
        settings.EXTERNAL_PROCESSING_APPROVAL_ID,
        tuple(
            value.strip()
            for value in settings.EXTERNAL_PROCESSING_ALLOWED_ENDPOINTS.split(",")
            if value.strip()
        ),
    )


def _material_context(sources: tuple[str, ...], known_values: tuple[str, ...] = ()):
    spans = identifier_spans(sources, detect_identifiers, known_values)
    known = tuple(
        {
            source[span.start : span.end]
            for source, own in zip(sources, spans, strict=True)
            for span in own
        }
    )
    return known, spans


def _require_destination(policy: ExternalProcessingPolicy, endpoint: str) -> None:
    policy.require(endpoint)
    try:
        url = urlsplit(endpoint)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError
        _ = url.port
    except ValueError:
        raise PrivacyRejected("Некорректный адрес внешнего провайдера.") from None


def _restore(value, session: PseudonymSession):
    if isinstance(value, str):
        return session.restore(value)
    if isinstance(value, list):
        return [_restore(item, session) for item in value]
    if isinstance(value, dict):
        restored = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PrivacyRejected("Некорректный JSON внешней модели.")
            key = session.restore(key)
            if key in restored:
                raise PrivacyRejected("Неоднозначные поля ответа внешней модели.")
            restored[key] = _restore(item, session)
        return restored
    if value is None or type(value) in (int, float, bool):
        return value
    raise PrivacyRejected("Некорректный JSON внешней модели.")


class GuardedLLMClient:
    def __init__(
        self,
        backend,
        endpoint: str,
        policy: ExternalProcessingPolicy,
        known_values: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
        source_spans: tuple = (),
    ):
        self.backend = backend
        self.endpoint = endpoint
        self.policy = policy
        self.known_values = known_values
        self.sources = sources
        self.source_spans = source_spans
        self.receipts: list[dict] = []

    def with_materials(self, sources: tuple[str, ...]):
        known, spans = _material_context(sources, self.known_values)
        return GuardedLLMClient(self.backend, self.endpoint, self.policy, known, sources, spans)

    async def complete_json(self, system: str, user: str) -> dict:
        try:
            _require_destination(self.policy, self.endpoint)
        except Exception:
            raise ProcessingNotApproved() from None
        try:
            fragment = expand_source_fragment(user, self.sources, self.source_spans)
            if fragment.matched:
                if fragment.text is None:
                    raise PrivacyRejected("Неоднозначный фрагмент исходного документа.")
                user = fragment.text
            masked = anonymize_texts(
                (system, user), detect_identifiers, uuid.uuid4().hex, self.known_values
            )
            instructions = (
                "\nИдентификаторы заменены непрозрачными метками. В цитатах копируй метки "
                "точно; не угадывай скрытые имена, даты, возраст или правовые факты. "
                "Если скрытого значения не хватает для вывода, верни null."
            )
            result = await self.backend.complete_json(
                masked.texts[0] + instructions, masked.texts[1]
            )
            if not isinstance(result, dict):
                raise PrivacyRejected("Некорректный JSON внешней модели.")
            restored = _restore(result, masked.session)
            model = getattr(self.backend, "last_requested_model", None)
            self.receipts.append(
                {
                    "provider_adapter": type(self.backend).__name__,
                    "requested_model": model if isinstance(model, str) else None,
                    "endpoint_sha256": sha256(self.endpoint.encode()).hexdigest(),
                    "system_prompt_sha256": sha256(system.encode()).hexdigest(),
                    "privacy_instructions_sha256": sha256(instructions.encode()).hexdigest(),
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            record_receipt(self.receipts[-1])
            return restored
        except LLMError as exc:
            message = (
                f"Внешняя модель вернула ошибку HTTP {exc.status}."
                if exc.status
                else "Ошибка внешней языковой модели."
            )
            raise LLMError(message, status=exc.status) from None
        except Exception:
            raise LLMError("Не удалось безопасно обработать ответ внешней модели.") from None


class GuardedEmbeddings:
    def __init__(
        self,
        backend,
        endpoint: str,
        policy: ExternalProcessingPolicy,
        known_values: tuple[str, ...] = (),
        sources: tuple[str, ...] = (),
        source_spans: tuple = (),
    ):
        self.backend, self.endpoint, self.policy = backend, endpoint, policy
        self.known_values, self.sources, self.source_spans = known_values, sources, source_spans

    def with_materials(self, sources: tuple[str, ...]):
        known, spans = _material_context(sources, self.known_values)
        return GuardedEmbeddings(self.backend, self.endpoint, self.policy, known, sources, spans)

    async def embed(self, texts: list[str], task: str) -> list[list[float]]:
        try:
            _require_destination(self.policy, self.endpoint)
        except Exception:
            raise EmbeddingError(
                "Внешняя обработка данных не согласована для этого провайдера."
            ) from None
        try:
            expanded = []
            for text in texts:
                fragment = expand_source_fragment(text, self.sources, self.source_spans)
                if fragment.matched and fragment.text is None:
                    raise PrivacyRejected("Неоднозначный фрагмент исходного документа.")
                expanded.append(fragment.text if fragment.matched else text)
            masked = anonymize_texts(
                tuple(expanded), detect_identifiers, uuid.uuid4().hex, self.known_values
            )
            safe = [re.sub(r"\[JAI_[a-f0-9]{32}_\d+\]", "скрыто", text) for text in masked.texts]
            safe = [" ".join(text.split())[:8000] for text in safe]
            return await self.backend.embed(safe, task)
        except Exception:
            raise EmbeddingError("Ошибка внешнего сервиса эмбеддингов.") from None
