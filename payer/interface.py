from abc import ABC, abstractmethod
from typing import Literal

PayerCallState = Literal["connected", "on_hold", "dropped", "unreachable"]


class PayerInterface(ABC):
    """
    The boundary between the agent core and any payer implementation
    (mock or, eventually, real telephony).
    """

    @abstractmethod
    def ivr_prompt(self) -> str:
        """Return the current IVR menu text."""

    @abstractmethod
    def send_dtmf(self, digit: str) -> None:
        """Navigate the phone menu by 'pressing' a key."""

    @abstractmethod
    def ask(self, question: str) -> str:
        """
        Ask the representative a question.
        Returns free-text answer — may be messy, contradictory, or off-script.
        MUST NOT receive raw member IDs.
        """

    @abstractmethod
    def call_state(self) -> PayerCallState:
        """Return the current call state."""
