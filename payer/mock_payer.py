from __future__ import annotations
import yaml
import re
from pathlib import Path
from .interface import PayerInterface, PayerCallState
from models import InjectConfig
from core.crypto import PayerCrypto


class MockPayer(PayerInterface):
    """
    Fixture-driven payer simulator.

    Loads a YAML fixture that defines:
      - ivr:        the menu tree (root text + digit→text branches)
      - rep_answers: dict mapping question-intent key → answer string
      - inject:     failure knobs (drop, unreachable, contradict, transfer)

    The simulator is intentionally messy — answers are free-text and
    may be inconsistent, just like a real rep call.
    """

    def __init__(self, fixture_path: str | Path) -> None:
        raw = yaml.safe_load(Path(fixture_path).read_text())
        self._ivr: dict     = raw.get("ivr", {})
        self._answers: dict = raw.get("rep_answers", {})
        self._inject        = self._parse_inject(raw.get("inject", {}))

        self._current_ivr_node: str = "root"
        self._total_questions_asked: int = 0
        self._questions_asked: dict[str, int] = {}
        self._state: PayerCallState = "unreachable" if self._inject.unreachable else "connected"
        self._second_answer_given: set[str] = set()
        self.received_member_id: str | None = None

    # ------------------------------------------------------------------
    # PayerInterface implementation
    # ------------------------------------------------------------------

    def ivr_prompt(self) -> str:
        return self._ivr.get(self._current_ivr_node, "")

    def send_dtmf(self, digit: str) -> None:
        if digit in self._ivr:
            self._current_ivr_node = digit
            # Simulate going on hold after navigating to a department
            if "hold" in self._ivr.get(digit, "").lower():
                self._state = "on_hold"

    def ask(self, question: str) -> str:
        if self._state == "on_hold":
            self._state = "connected"   # rep picked up

        self._total_questions_asked += 1
        
        # Intercept and decrypt member ID if present
        match = re.search(r"\[ENC:(.*?)\]", question)
        if match and not self.received_member_id:
            token = match.group(0)
            decrypted_id = PayerCrypto.decrypt_member_id(token)
            if decrypted_id:
                self.received_member_id = decrypted_id
                print(f"\n\033[95m[MockPayer] 🔓 Successfully decrypted member ID: {decrypted_id}\033[0m")
        
        # Inject: drop after N questions
        if (
            self._inject.drop_after_question is not None
            and self._total_questions_asked >= self._inject.drop_after_question
        ):
            self._state = "dropped"
            return ""

        # Inject: transfer on specific intent keyword
        if self._inject.transfer_on and self._inject.transfer_on.lower() in question.lower():
            self._state = "on_hold"
            return "Let me transfer you to the claims department."

        # Match question to an intent key (simple substring match — production would use LLM)
        intent_key = self._match_intent(question)
        self._questions_asked[intent_key] = self._questions_asked.get(intent_key, 0) + 1
        answer = self._answers.get(intent_key, "I'm not sure about that.")
        
        # Inject: contradictory second answer
        if (
            self._inject.contradict
            and intent_key == self._inject.contradict.get("field")
            and intent_key not in self._second_answer_given
            and self._questions_asked[intent_key] > 1
        ):
            self._second_answer_given.add(intent_key)
            answer = self._inject.contradict["second_answer"]

        return answer

    def call_state(self) -> PayerCallState:
        return self._state

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _match_intent(self, question: str) -> str:
        """
        Word-level match against known intent keys.
        Checks whether significant words from the key appear in the question.
        Good enough for the mock; the real agent uses LLM matching.
        """
        q_lower = question.lower()
        best_key, best_score = "__unknown__", 0

        for key in self._answers:
            words = [w for w in key.split("_") if len(w) > 2]
            # Also expand common abbreviations so "auth" matches "authorization"
            expanded = {
                "auth": "authoriz",
                "prior": "prior",
                "copay": "copay",
                "coverage": "coverage",
                "active": "active",
                "visit": "visit",
                "limit": "limit",
                "denial": "denial",
                "missing": "missing",
            }
            score = sum(
                1 for w in words
                if expanded.get(w, w) in q_lower or w in q_lower
            )
            if score > best_score:
                best_score, best_key = score, key

        return best_key if best_score > 0 else "__unknown__"

    @staticmethod
    def _parse_inject(raw: dict) -> InjectConfig:
        return InjectConfig(
            drop_after_question=raw.get("drop_after_question"),
            unreachable=raw.get("unreachable", False),
            contradict=raw.get("contradict"),
            transfer_on=raw.get("transfer_on"),
        )
