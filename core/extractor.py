"""
Extractor + Reconciler

Extractor  — uses LLM to parse each messy answer into a typed value.
Reconciler — purely deterministic: detects contradictions, computes confidence.

LLM usage: extractor only. Reconciler is 100% rule-based.
"""
from dataclasses import dataclass, field
from core.qa_loop import QATurn
from llm.interface import LLMInterface, ExtractionResult
from models.scenario import ScenarioConfig
from core.live_logger import LiveLogger, SILENT

CONFIDENCE_FLOOR = 0.5  # below this, field is treated as missing


@dataclass
class ExtractedField:
    key: str
    value: str | None
    confidence: float
    raw_answer: str


@dataclass
class ReconciliationReport:
    fields: list[ExtractedField] = field(default_factory=list)
    contradictions: list[dict[str, str]] = field(default_factory=list)
    overall_confidence: float = 0.0
    missing_required: list[str] = field(default_factory=list)


# Map from intent key → expected field type (extend as needed)
FIELD_TYPES: dict[str, str] = {
    "coverage_active":  "boolean",
    "copay":            "currency",
    "visit_limit":      "integer",
    "prior_auth":       "boolean",
    "denial_reason":    "text",
    "missing_docs":     "text",
    "auth_status":      "text",
    "auth_missing":     "text",
}


class Extractor:
    def __init__(self, llm: LLMInterface) -> None:
        self._llm = llm

    def extract_all(
        self,
        transcript: list[QATurn],
        scenario: ScenarioConfig,
        logger: LiveLogger | None = None,
    ) -> dict[str, ExtractedField]:
        log = logger or SILENT
        results: dict[str, ExtractedField] = {}
        log.extract_start()

        for turn in transcript:
            if turn.intent_key.startswith("__"):
                continue  # skip meta-turns (transfers, etc.)

            field_type = FIELD_TYPES.get(turn.intent_key, "text")
            extraction: ExtractionResult = self._llm.extract(
                question=turn.question,
                answer=turn.answer,
                field_type=field_type,
            )

            # Off-script turns get their confidence halved
            confidence = extraction.confidence / 2 if turn.off_script else extraction.confidence

            results[turn.intent_key] = ExtractedField(
                key=turn.intent_key,
                value=extraction.value if confidence >= CONFIDENCE_FLOOR else None,
                confidence=confidence,
                raw_answer=turn.answer,
            )
            log.field_extracted(
                turn.intent_key,
                results[turn.intent_key].value,
                confidence,
                off_script=turn.off_script,
            )

        return results


class Reconciler:
    """
    Deterministic post-processing:
      1. Detect contradictions across transcript turns.
      2. Check required fields are present.
      3. Compute overall confidence (mean of per-field confidences).
    """

    def reconcile(
        self,
        fields: dict[str, ExtractedField],
        transcript: list[QATurn],
        scenario: ScenarioConfig,
    ) -> ReconciliationReport:
        report = ReconciliationReport()
        report.fields = list(fields.values())

        # Detect contradictions between primary answer and confirmation answer
        primary: dict[str, str] = {}
        for turn in transcript:
            key = turn.intent_key
            if key.startswith("__"):
                continue
            if key.endswith("__confirm"):
                base_key = key.replace("__confirm", "")
                if base_key in primary and fields.get(base_key):
                    confirm_extraction = self._extract_confirm_value(turn, fields.get(base_key))
                    if confirm_extraction and confirm_extraction != primary[base_key]:
                        report.contradictions.append({
                            "field": base_key,
                            "first": primary[base_key],
                            "second": confirm_extraction,
                        })
            elif key in fields and fields[key].value is not None:
                primary[key] = fields[key].value

        # Missing required fields
        for req in scenario.required_fields:
            f = fields.get(req)
            if f is None or f.value is None:
                report.missing_required.append(req)

        # Overall confidence
        if fields:
            report.overall_confidence = sum(f.confidence for f in fields.values()) / len(fields)

        return report

    @staticmethod
    def _extract_confirm_value(turn: QATurn, primary_field: ExtractedField) -> str | None:
        """Quick extraction of the confirmation answer for comparison."""
        import re
        answer = turn.answer.lower()
        if primary_field.confidence > 0 and primary_field.value is not None:
            # For currency: look for any dollar amount
            match = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", turn.answer)
            if match:
                return match.group(1)
        return None
