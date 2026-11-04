"""Repeat existing matching/statistics over an immutable, subject-owned candidate bank."""

import json

from legal_core.precedents import PrecedentCard, PrecedentEpisode, Recidivism, parse_qualifications

from src.application.practice_report import compare_draft_with_practice
from src.domain.circumstance_codes import circumstance_codes
from src.infrastructure.calculation_inputs import _json_value, load_inputs, replay_inputs
from src.schemas.analysis import LegalCheck
from src.services.sentence_checks import recidivism_of

RESET_WARNING = (
    "После изменения фактов прежние рекомендации и сравнение с практикой сняты. "
    "Требуется повторный отбор практики."
)
POOL_WARNING = (
    "Практика повторно отобрана только из сохранённой выборки. Новый поиск по корпусу "
    "не выполнялся; ранее исключённые и новые материалы в эту выборку не входят. "
    "Стадия преступления и временная применимость норм автоматически не сверены."
)


class FrozenCandidateStore:
    """Read ports only. No DB/provider handles or writes exist on this adapter."""

    def __init__(self, candidates):
        self.cards = {}
        for candidate in candidates:
            stored = candidate.stored
            if stored.id in self.cards and self.cards[stored.id] != stored:
                raise ValueError("Conflicting saved candidate")
            self.cards[stored.id] = stored

    async def qualification_channel(self, keys, limit):
        # The core filters, including same-article, decide admissibility. This bank
        # contains only previously retained cards, not a fresh corpus retrieval.
        return list(self.cards)[:limit]

    async def fulltext_channel(self, text, limit):
        return list(self.cards)[:limit]

    async def load(self, ids):
        return {key: self.cards[key] for key in ids if key in self.cards}


class NoNetworkEmbedder:
    model_name = "frozen-pool/no-vector"

    async def embed_query(self, text):
        return None


def _candidate_pool(report):
    pool = list(report.candidate_pool)
    if not pool:
        for episode in report.episodes:
            pool.extend(episode.candidate_pool)
    return pool or list(report.shown)


def corrected_query(prepared, result, original):
    sentence = prepared.sentence
    if sentence is None or not sentence.counts:
        raise ValueError("Нет подтверждённых эпизодов для повторного отбора практики.")
    if "conditional" in prepared.unknown_fields:
        raise ValueError(
            "Условность осуждения не установлена; повторный отбор практики не выполнен."
        )
    if any(c.established is None for c in (*prepared.mitigating, *prepared.aggravating)):
        raise ValueError(
            "Статус обстоятельства не установлен; повторный отбор практики не выполнен."
        )
    if any(
        not circumstance_codes(c.norm)
        for c in (*prepared.mitigating, *prepared.aggravating)
        if c.established is True
    ):
        raise ValueError(
            "Ссылка на норму обстоятельства не распознана; "
            "уточните её для повторного отбора практики."
        )
    if any(key.startswith("fine_credit/") for key in prepared.unknown_fields):
        raise ValueError(
            "Сведения о зачёте штрафа не установлены; повторный отбор практики не выполнен."
        )
    episodes = []
    for index, count in enumerate(sentence.counts):
        found = parse_qualifications(count.qualification) if count.reference is not None else ()
        if len(found) != 1:
            raise ValueError(
                "Квалификация эпизода не установлена; повторный отбор практики не выполнен."
            )
        term = None if f"count/{index}/main" in prepared.unknown_fields else count.main
        episodes.append(PrecedentEpisode(found[0], term))
    known = recidivism_of(
        [LegalCheck.model_validate(check) for check in result.get("legal_checks", [])]
    )
    recidivism = Recidivism(known.value) if known.value in {r.value for r in Recidivism} else None
    rules = set(original.applied_general) - {"64", "73"}
    if any(fact.value is True for fact in prepared.art64_by_count):
        rules.add("64")
    if sentence.conditional:
        rules.add("73")
    mitigating = frozenset(
        code
        for item in prepared.mitigating
        if item.established is True
        for code in circumstance_codes(item.norm)
    )
    aggravating = frozenset(
        code
        for item in prepared.aggravating
        if item.established is True
        for code in circumstance_codes(item.norm)
    )
    return PrecedentCard(
        episodes=tuple(episodes),
        mitigating=mitigating,
        aggravating=aggravating,
        recidivism=recidivism,
        applied_general=frozenset(rules),
        final=None if "final" in prepared.unknown_fields else sentence.final,
        conditional=sentence.conditional,
        fabula=original.fabula,
        fine_credits=sentence.fine_credits,
    )


async def refresh_frozen_practice(payload, result):
    snapshot = load_inputs(payload)
    if "practice" not in snapshot.review_invalidations:
        return payload, result
    if snapshot.review_practice_baseline is None:
        if len(snapshot.kwargs.prepared_sentencing_inputs) == 1:
            root = snapshot.kwargs.practice
            snapshot.review_practice_baseline = {0: root} if root is not None else {}
        else:
            snapshot.review_practice_baseline = dict(snapshot.kwargs.defendant_practice or {})
    baseline = snapshot.review_practice_baseline
    refreshed, statuses = {}, {}
    warnings = [
        w for w in snapshot.kwargs.extra_warnings if w != RESET_WARNING and w != POOL_WARNING
    ]
    people = result.get("defendants") or []
    for subject, prepared in snapshot.kwargs.prepared_sentencing_inputs.items():
        saved = baseline.get(subject)
        if saved is None:
            statuses[str(subject)] = {
                "status": "unavailable",
                "reason": "Для этого лица не сохранена исходная выборка практики.",
                "pool_size": 0,
            }
            continue
        candidates = _candidate_pool(saved)
        store = FrozenCandidateStore(candidates)
        try:
            query = corrected_query(prepared, people[subject] if people else result, saved.query)
        except ValueError as exc:
            statuses[str(subject)] = {
                "status": "unavailable",
                "reason": str(exc),
                "pool_size": len(store.cards),
            }
            continue
        report = await compare_draft_with_practice(
            store, NoNetworkEmbedder(), query, statistics_pool=max(50, len(store.cards))
        )
        refreshed[subject] = report
        statuses[str(subject)] = {
            "status": "refiltered",
            "pool_size": len(store.cards),
            "basis": "retained_candidates"
            if saved.candidate_pool or any(e.candidate_pool for e in saved.episodes)
            else "shown_only",
            "vector_used": False,
        }
    snapshot.kwargs.practice = refreshed.get(0) if not people else None
    snapshot.kwargs.defendant_practice = refreshed if people else None
    snapshot.review_invalidations = []
    snapshot.review_practice_refresh = {"version": "frozen-practice-review/1", "subjects": statuses}
    for subject, state in statuses.items():
        if state["status"] == "unavailable":
            warnings.append(f"Осуждённый {int(subject) + 1}: {state['reason']}")
        elif state["basis"] == "shown_only":
            warnings.append(
                f"Осуждённый {int(subject) + 1}: сохранён только ранее показанный список аналогов; "
                "выборка ограничена этим списком."
            )
    if refreshed:
        warnings.append(POOL_WARNING)
    snapshot.kwargs.extra_warnings = list(dict.fromkeys(warnings))
    snapshot.provenance = {
        **(snapshot.provenance or {}),
        "practice_review": snapshot.review_practice_refresh,
    }
    updated = json.loads(
        json.dumps(_json_value(snapshot.model_dump(mode="python")), allow_nan=False)
    )
    return updated, replay_inputs(updated).model_dump(mode="json", by_alias=True)
