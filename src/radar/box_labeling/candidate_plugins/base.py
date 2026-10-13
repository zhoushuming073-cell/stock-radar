from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CandidateResult:
    passed: bool
    score: float
    diagnostics: Mapping[str, float | int | bool | str]
    rejection_reasons: tuple[str, ...]
