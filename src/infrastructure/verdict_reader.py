"""Adapter: the regex VerdictReader used for both drafts and practice verdicts."""

import re

from src.application.precedent_cards import VerdictReading
from src.infrastructure.circumstance_extractor import extract_circumstances
from src.infrastructure.fabula import extract_fabula
from src.infrastructure.ruling_reader import RulingReader, is_ruling
from src.services.defendant_blocks import defendant_names, scoped_verdicts
from src.services.punishment_extractor import extract_imposed_sentence
from src.services.verdict_segmenter import VerdictSegments, segment_verdict

_ACQUITTAL_DECISION = re.compile(
    r"^[ \t]*(?:оправдать\b|признать[^\n]{1,100}\s+невиновн"
    r"|ФИО\d+\s+по\s+предъявленному[^\n]{0,220}\bоправдать\b)",
    re.IGNORECASE | re.MULTILINE,
)


class RegexVerdictReader:
    def read(self, text: str) -> VerdictReading:
        return self._read(segment_verdict(text))

    def _read(self, segments: VerdictSegments) -> VerdictReading:
        sentence = extract_imposed_sentence(segments.operative, segments.description).sentence
        circumstances = extract_circumstances(
            segments.description, segments.operative, segments.introduction
        )
        return VerdictReading(
            introduction=segments.introduction,
            description=segments.description,
            operative=segments.operative,
            sentence=sentence,
            fabula=extract_fabula(segments.description),
            mitigating=circumstances.mitigating,
            aggravating=circumstances.aggravating,
            applied_general=circumstances.applied_general,
            recidivism=circumstances.recidivism,
            recidivism_quote=circumstances.recidivism_quote,
        )

    def read_all(self, text: str) -> list[VerdictReading]:
        return [self.read(text)]


class PracticeReader(RegexVerdictReader):
    """Reader of the practice base: a ruling gives a reading per convicted person."""

    def read_all(self, text: str) -> list[VerdictReading]:
        if is_ruling(text):
            return RulingReader().read_all(text)
        operative = segment_verdict(text).operative
        # Only explicit operative decisions count. A defence request in the description
        # does not make an acquittal; mixed verdicts still retain their convicted people.
        if _ACQUITTAL_DECISION.search(operative) and not defendant_names(operative):
            return []
        scoped = scoped_verdicts(text)
        return (
            [self.read(person_text) for _, person_text in scoped] if scoped else [self.read(text)]
        )
