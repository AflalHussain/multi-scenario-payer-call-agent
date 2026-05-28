"""
Result Builder

Assembles the final CallResult from reconciliation output.
This is the enforcer of the no-fabrication rule: any missing required
field or contradiction produces BLOCKED, never COMPLETE.
"""
from core.extractor import ReconciliationReport, ExtractedField
from core.qa_loop import QATurn
from models.result import CallResult, ResultStatus
from models.scenario import ScenarioConfig

CONTRADICTION_CONFIDENCE_PENALTY = 0.3   # applied per contradiction found


class ResultBuilder:
    def build(
        self,
        scenario: ScenarioConfig,
        transcript: list[QATurn],
        report: ReconciliationReport,
        blocked_reason: str | None = None,
    ) -> CallResult:
        """
        Produce the final CallResult.

        blocked_reason is set externally when the call itself failed
        (drop, unreachable) before extraction even ran.
        """

        # Was the call hard-blocked before extraction?
        if blocked_reason:
            return self._blocked(scenario, transcript, report, blocked_reason)

        # Missing required fields → BLOCKED
        if report.missing_required:
            missing = ", ".join(report.missing_required)
            return self._blocked(
                scenario, transcript, report,
                f"Required fields could not be extracted: {missing}",
            )

        # Contradictions → BLOCKED (never guess which answer is right)
        if report.contradictions:
            fields = ", ".join(c["field"] for c in report.contradictions)
            return self._blocked(
                scenario, transcript, report,
                f"Contradictory answers detected for: {fields}",
            )

        # Confidence too low → BLOCKED
        penalised = report.overall_confidence - (
            len(report.contradictions) * CONTRADICTION_CONFIDENCE_PENALTY
        )
        if penalised < 0.5:
            return self._blocked(
                scenario, transcript, report,
                f"Overall confidence too low ({penalised:.2f})",
            )

        # All checks passed → COMPLETE
        return CallResult(
            status=ResultStatus.COMPLETE,
            scenario=scenario.name,
            extracted_data={f.key: f.value for f in report.fields},
            confidence=round(penalised, 3),
            field_confidence={f.key: round(f.confidence, 3) for f in report.fields},
            transcript=self._serialise_transcript(transcript),
            contradictions=report.contradictions,
        )

    # ------------------------------------------------------------------

    def _blocked(
        self,
        scenario: ScenarioConfig,
        transcript: list[QATurn],
        report: ReconciliationReport,
        reason: str,
    ) -> CallResult:
        return CallResult(
            status=ResultStatus.BLOCKED,
            scenario=scenario.name,
            extracted_data={f.key: f.value for f in report.fields},
            confidence=round(report.overall_confidence, 3),
            field_confidence={f.key: round(f.confidence, 3) for f in report.fields},
            reason=reason,
            transcript=self._serialise_transcript(transcript),
            contradictions=report.contradictions,
        )

    @staticmethod
    def _serialise_transcript(transcript: list[QATurn]) -> list[dict[str, str]]:
        return [
            {
                "intent": t.intent_key,
                "question": t.question,
                "answer": t.answer,
                "retries": str(t.retries),
                "off_script": str(t.off_script),
            }
            for t in transcript
        ]
