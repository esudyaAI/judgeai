"""Use case: read the structure of uploaded verdict documents before the model sees them.

Splits each document into parts, prepares prompt texts that keep the introductory and
operative parts whole, and reads the imposed punishment from the operative part by regex.
"""

from dataclasses import dataclass, replace

from legal_core.entities import CountSentence, ImposedSentence, PunishmentTerm

from src.services.defendant_blocks import scoped_verdicts
from src.services.punishment_extractor import extract_imposed_sentence
from src.services.qualification_reference import parse_qualification_reference
from src.services.verdict_segmenter import VerdictSegments, segment_verdict


@dataclass(frozen=True)
class VerdictStructure:
    segments: tuple[VerdictSegments, ...]
    model_texts: list[str]
    sentence: ImposedSentence
    ambiguous_windows: tuple[str, ...]
    defendant_sentences: tuple[ImposedSentence, ...] = ()

    def with_resolved_windows(
        self, resolved: list[tuple[str, PunishmentTerm | None]]
    ) -> ImposedSentence:
        """Adds counts read by the LLM from windows the regex could not parse."""
        extra = []
        for window, term in resolved:
            if term is None:
                continue
            reference = parse_qualification_reference(window)
            extra.append(
                CountSentence(str(reference) if reference else "", reference, term, (), window)
            )
        return replace(self.sentence, counts=self.sentence.counts + tuple(extra))


def read_verdict_structure(texts: list[str], chars_limit: int) -> VerdictStructure:
    segments = tuple(segment_verdict(text) for text in texts)
    filled = sum(1 for text in texts if text.strip()) or 1
    per_document = chars_limit // filled
    model_texts = [
        part.model_context(per_document) if part.recognized else text
        for part, text in zip(segments, texts, strict=True)
    ]
    scoped = [person for text in texts for person in scoped_verdicts(text)]
    multiple = bool(scoped)
    operative = next((part.operative for part in segments if part.operative), "")
    extraction = extract_imposed_sentence(
        operative,
        "\n".join(p.description for p in segments),
        introduction="\n".join(p.introduction for p in segments),
    )
    return VerdictStructure(
        segments,
        model_texts,
        ImposedSentence() if multiple else extraction.sentence,
        () if multiple else extraction.ambiguous_windows,
        tuple(
            extract_imposed_sentence(
                (person_segments := segment_verdict(text)).operative,
                person_segments.description,
                introduction=person_segments.introduction,
            ).sentence
            for _, text in scoped
        ),
    )
