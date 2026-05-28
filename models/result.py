from dataclasses import dataclass, field
from enum import Enum


class ResultStatus(Enum):
    COMPLETE = "complete"   # all required fields extracted with acceptable confidence
    BLOCKED  = "blocked"    # needs human review; reason is always populated


@dataclass
class CallResult:
    """
    The structured output of a payer call.

    Rules (graded constraint):
      - status must NEVER be COMPLETE when a required field is missing or confidence < threshold.
      - reason must ALWAYS be populated when status is BLOCKED.
      - extracted_data must NEVER contain guessed or fabricated values.
    """
    status: ResultStatus
    scenario: str                              # e.g. "benefits_verification"
    extracted_data: dict[str, str | None]      # keyed by question intent
    confidence: float                          # 0.0 – 1.0 across all fields
    field_confidence: dict[str, float] = field(default_factory=dict)  # per-field breakdown
    reason: str | None = None                  # populated on BLOCKED; explains why
    transcript: list[dict[str, str]] = field(default_factory=list)    # full Q&A log
    contradictions: list[dict[str, str]] = field(default_factory=list) # detected conflicts

    @property
    def needs_human(self) -> bool:
        return self.status == ResultStatus.BLOCKED

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "scenario": self.scenario,
            "confidence": round(self.confidence, 3),
            "extracted_data": self.extracted_data,
            "field_confidence": {k: round(v, 3) for k, v in self.field_confidence.items()},
            "reason": self.reason,
            "contradictions": self.contradictions,
            "transcript": self.transcript,
        }
