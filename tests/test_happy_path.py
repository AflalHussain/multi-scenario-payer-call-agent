"""
Golden transcript tests — verify that clean fixtures produce COMPLETE results
with the expected extracted values.
"""
import pytest
from core.agent import PayerCallAgent
from models.result import ResultStatus

SCENARIOS = "scenarios"
FIXTURES  = "fixtures"


@pytest.fixture
def agent():
    return PayerCallAgent()


class TestBenefitsClean:
    def test_status_is_complete(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_clean.yaml",
            member_id="MBR-SYNTH-001",
        )
        assert result.status == ResultStatus.COMPLETE

    def test_coverage_active_extracted(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_clean.yaml",
        )
        assert result.extracted_data.get("coverage_active") == "true"

    def test_confidence_above_threshold(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_clean.yaml",
        )
        assert result.confidence >= 0.5

    def test_no_contradictions(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_clean.yaml",
        )
        assert result.contradictions == []

    def test_transcript_contains_all_questions(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_clean.yaml",
        )
        keys = {t["intent"] for t in result.transcript}
        assert "coverage_active" in keys
        assert "copay" in keys
