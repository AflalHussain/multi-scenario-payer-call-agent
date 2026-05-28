"""
IVR Navigator — fully deterministic, zero LLM calls.

Reads the ivr_path from the scenario config and presses the correct
DTMF digits in order. Detects when the call drops mid-navigation.
"""
from payer.interface import PayerInterface
from models.call_state import CallState
from core.live_logger import LiveLogger, SILENT


class IVRNavigationError(Exception):
    pass


class IVRNavigator:
    def __init__(self, payer: PayerInterface, ivr_path: list[str],
                 logger: LiveLogger | None = None) -> None:
        self._payer    = payer
        self._ivr_path = ivr_path
        self._logger   = logger or SILENT

    def navigate(self) -> CallState:
        """
        Press each digit in ivr_path in sequence.
        Returns the resulting CallState (WAITING_FOR_REP on success, BLOCKED on failure).
        """
        log   = self._logger
        state = self._payer.call_state()

        if state == "unreachable":
            return CallState.BLOCKED

        log.ivr_prompt(self._payer.ivr_prompt())

        for digit in self._ivr_path:
            state = self._payer.call_state()
            if state in ("dropped", "unreachable"):
                return CallState.BLOCKED

            log.ivr_press(digit)
            self._payer.send_dtmf(digit)

            # After navigating, check for hold (rep dept reached)
            if self._payer.call_state() == "on_hold":
                log.on_hold()

        return CallState.WAITING_FOR_REP
