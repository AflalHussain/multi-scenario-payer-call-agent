"""
Agent Core — the single entry point for running any payer call scenario.

Usage
-----
    from core.agent import PayerCallAgent
    from llm.stub import StubLLM
    from llm.openrouter import OpenRouterLLM

    # Use stub (no key) or OpenRouter:
    result = PayerCallAgent(StubLLM()).run(
    # result = PayerCallAgent(OpenRouterLLM()).run(
        scenario_path="scenarios/benefits_verification.yaml",
        fixture_path="fixtures/benefits_clean.yaml",
        member_id="MBR-001-SYNTHETIC",
    )
    print(result.to_dict())

State machine
-------------
INITIALIZING → DIALING → NAVIGATING_IVR → WAITING_FOR_REP
    → ASKING → EXTRACTING → COMPLETE | BLOCKED

Any failure at any stage short-circuits to BLOCKED.
"""
from __future__ import annotations
import yaml
from pathlib import Path

from payer.mock_payer import MockPayer
from llm.interface import LLMInterface
from llm.stub import StubLLM
from llm.openrouter import OpenRouterLLM
from models.call_state import CallState
from models.result import CallResult, ResultStatus
from models.scenario import ScenarioConfig, IVRConfig

from core.ivr_navigator import IVRNavigator
from core.qa_loop import QALoop, QAResult
from core.extractor import Extractor, Reconciler, ReconciliationReport
from core.result_builder import ResultBuilder
from core.live_logger import LiveLogger, SILENT


def _load_scenario(path: str | Path) -> ScenarioConfig:
    raw = yaml.safe_load(Path(path).read_text())
    return ScenarioConfig(
        name=raw["scenario"],
        ivr_path=raw.get("ivr_path", []),
        questions=raw.get("questions", []),
        required_fields=raw.get("required_fields", []),
        nullable_fields=raw.get("nullable_fields", []),
        metadata=raw.get("metadata", {}),
    )


class PayerCallAgent:
    """
    One agent core, config-driven.
    Adding a fourth scenario requires no changes here.
    """

    def __init__(self, llm: LLMInterface | None = None, logger: LiveLogger | None = None) -> None:
        self._llm    = llm or StubLLM()
        self._logger = logger or SILENT
        self._extractor   = Extractor(self._llm)
        self._reconciler  = Reconciler()
        self._builder     = ResultBuilder()

    def run(
        self,
        scenario_path: str | Path,
        fixture_path: str | Path,
        member_id: str | None = None,
    ) -> CallResult:
        """
        Execute a full payer call and return a structured result.

        Parameters
        ----------
        scenario_path : path to a scenario YAML (benefits / denial / auth / ...)
        fixture_path  : path to a fixture YAML (drives the mock payer behaviour)
        member_id     : patient member ID — masked before crossing the payer boundary
        """
        log = self._logger

        # ── INITIALIZING ──────────────────────────────────────────────
        scenario = _load_scenario(scenario_path)
        payer    = MockPayer(fixture_path)
        state    = CallState.INITIALIZING
        log.call_start(str(scenario_path), str(fixture_path))
        log.state_change("INITIALIZING")

        # ── DIALING ───────────────────────────────────────────────────
        state = CallState.DIALING
        log.state_change("DIALING", f"scenario={scenario.name}")
        if payer.call_state() == "unreachable":
            log.call_unreachable()
            result = self._hard_block(scenario, "Payer unreachable")
            log.final_result(result.status.value, result.confidence, result.reason)
            return result

        # ── NAVIGATING_IVR ────────────────────────────────────────────
        state = CallState.NAVIGATING_IVR
        log.state_change("NAVIGATING_IVR", f"path={scenario.ivr_path}")
        navigator = IVRNavigator(payer, scenario.ivr_path, logger=log)
        state = navigator.navigate()
        if state == CallState.BLOCKED:
            result = self._hard_block(scenario, "Call dropped during IVR navigation")
            log.final_result(result.status.value, result.confidence, result.reason)
            return result

        # ── WAITING_FOR_REP / ASKING ──────────────────────────────────
        state = CallState.ASKING
        log.state_change("ASKING")
        qa_loop = QALoop(payer, self._llm, member_id=member_id, logger=log)
        qa_result: QAResult = qa_loop.run(scenario.questions, required_fields=scenario.required_fields)

        if qa_result.final_state == CallState.BLOCKED:
            result = self._hard_block(scenario, qa_result.blocked_reason or "Call failed during Q&A")
            log.final_result(result.status.value, result.confidence, result.reason)
            return result

        # ── EXTRACTING ────────────────────────────────────────────────
        state = CallState.EXTRACTING
        log.state_change("EXTRACTING")
        fields = self._extractor.extract_all(qa_result.transcript, scenario, logger=log)
        report: ReconciliationReport = self._reconciler.reconcile(fields, qa_result.transcript, scenario)

        for c in report.contradictions:
            log.contradiction_found(c["field"], c["first"], c["second"])

        # ── COMPLETE | BLOCKED ────────────────────────────────────────
        result = self._builder.build(scenario, qa_result.transcript, report)
        log.final_result(result.status.value, result.confidence, result.reason)
        return result

    # ------------------------------------------------------------------

    def _hard_block(self, scenario: ScenarioConfig, reason: str) -> CallResult:
        """Produce a BLOCKED result with an empty transcript."""
        return CallResult(
            status=ResultStatus.BLOCKED,
            scenario=scenario.name,
            extracted_data={},
            confidence=0.0,
            reason=reason,
        )
