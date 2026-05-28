"""
Failure + ambiguity path tests.
Every unhappy path must produce BLOCKED, never COMPLETE.
"""
import pytest
from core.agent import PayerCallAgent
from models.result import ResultStatus

SCENARIOS = "scenarios"
FIXTURES  = "fixtures"


@pytest.fixture
def agent():
    return PayerCallAgent()


class TestUnreachable:
    def test_blocked(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/unreachable.yaml",
        )
        assert result.status == ResultStatus.BLOCKED

    def test_reason_populated(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/unreachable.yaml",
        )
        assert result.reason and len(result.reason) > 0

    def test_no_fabricated_data(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/unreachable.yaml",
        )
        # extracted_data should be empty — nothing was ever said
        assert result.extracted_data == {}


class TestDroppedCall:
    def test_blocked(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_drop.yaml",
        )
        assert result.status == ResultStatus.BLOCKED

    def test_reason_mentions_drop(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_drop.yaml",
        )
        assert result.reason is not None
        assert "drop" in result.reason.lower() or "call" in result.reason.lower()


class TestContradiction:
    def test_blocked(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_contradiction.yaml",
        )
        assert result.status == ResultStatus.BLOCKED

    def test_contradiction_recorded(self, agent):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_contradiction.yaml",
        )
        assert len(result.contradictions) >= 1
        assert any(c["field"] == "copay" for c in result.contradictions)


class TestOffScript:
    def test_blocked_or_low_confidence(self, agent):
        """Off-script answers with exhausted retries → BLOCKED."""
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/benefits_offscript.yaml",
        )
        assert result.status == ResultStatus.BLOCKED


class TestTransfer:
    def test_transfer_does_not_fabricate(self, agent):
        """
        A mid-call transfer may result in BLOCKED if required fields
        weren't collected. The agent must not invent values.
        """
        result = agent.run(
            f"{SCENARIOS}/denied_claim.yaml",
            f"{FIXTURES}/denied_transfer.yaml",
        )
        # Either COMPLETE (if transfer recovered) or BLOCKED — never invented data
        if result.status == ResultStatus.COMPLETE:
            for v in result.extracted_data.values():
                assert v is not None, "Completed result must not contain None values"
        else:
            assert result.reason is not None


class TestNeverFabricatesSuccess:
    """
    Cross-cutting invariant: status COMPLETE must never appear
    when required fields are missing.
    """
    @pytest.mark.parametrize("fixture", [
        "benefits_drop.yaml",
        "benefits_contradiction.yaml",
        "benefits_offscript.yaml",
        "unreachable.yaml",
    ])
    def test_failure_fixtures_never_complete(self, agent, fixture):
        result = agent.run(
            f"{SCENARIOS}/benefits_verification.yaml",
            f"{FIXTURES}/{fixture}",
        )
        assert result.status == ResultStatus.BLOCKED, (
            f"Expected BLOCKED for {fixture}, got COMPLETE — possible fabrication"
        )
