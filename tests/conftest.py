import pytest
from core.agent import PayerCallAgent


@pytest.fixture(scope="session")
def agent():
    """Shared agent instance — StubLLM by default, no API key needed."""
    return PayerCallAgent()
