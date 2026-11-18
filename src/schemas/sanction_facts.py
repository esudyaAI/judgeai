from datetime import date

from pydantic import BaseModel


class SanctionFactItemRead(BaseModel):
    part: int | None
    kind: str
    role: str
    min_value: float | None
    max_value: float | None
    unit: str | None


class SanctionFactSourceRead(BaseModel):
    edition_label: str
    source_url: str
    provision_locator: str
    verification_status: str
    effective_from: date | None = None  # T45.9: period of force of the provision in the base
    effective_to: date | None = None


class SanctionFactRead(BaseModel):
    answered: bool
    method: str = "code"
    hint: str | None = None
    text: str | None = None
    qualification: str | None = None
    parsed: bool = False  # the base has the sanction of the asked part
    conflict: bool = False
    sanctions: list[SanctionFactItemRead] = []
    source: SanctionFactSourceRead | None = None
    on: date | None = None  # T45.9: the one date the question names
    in_force_on: bool | None = None  # the provision was in force on it; None — not known
