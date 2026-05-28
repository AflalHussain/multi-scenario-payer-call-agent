"""
Q&A Loop — drives the question/answer phase of the call.

Sensitive-data rule (graded constraint):
    Member ID is masked before crossing the ask() boundary.
    The agent substitutes a placeholder token; the mock payer never
    sees the real ID in the clear.

LLM usage:
    - is_off_script() is called on each answer to decide whether to retry.
    - All other logic (retry counting, transcript building) is deterministic.
"""
from dataclasses import dataclass, field
from payer.interface import PayerInterface
from llm.interface import LLMInterface
from models.call_state import CallState
from core.live_logger import LiveLogger, SILENT
from core.crypto import PayerCrypto

MAX_RETRIES = 1


@dataclass
class QATurn:
    intent_key: str
    question: str
    answer: str
    retries: int = 0
    off_script: bool = False


@dataclass
class QAResult:
    transcript: list[QATurn] = field(default_factory=list)
    final_state: CallState = CallState.ASKING
    blocked_reason: str | None = None


class QALoop:
    def __init__(
        self,
        payer: PayerInterface,
        llm: LLMInterface,
        member_id: str | None = None,
        logger: LiveLogger | None = None,
    ) -> None:
        self._payer    = payer
        self._llm      = llm
        self._member_id = member_id
        self._logger   = logger or SILENT

    def run(
        self,
        questions: list[dict[str, str]],
        required_fields: list[str] | None = None,
    ) -> QAResult:
        """
        Ask each question, then run a confirmation pass on required fields.
        The confirmation pass surfaces contradictions (the mock payer's
        second_answer injection fires on the re-ask).

        questions: [{"key": "coverage_active", "text": "Is the policy active?"}]
        required_fields: keys re-confirmed to catch contradictory second answers
        """
        result = QAResult()
        required_fields = set(required_fields or [])
        question_map = {q["key"]: q for q in questions}
        log = self._logger

        # ── Primary pass ───────────────────────────────────────────────
        for idx, q in enumerate(questions):
            state = self._payer.call_state()
            if state in ("dropped", "unreachable"):
                log.call_dropped(q["key"])
                result.final_state = CallState.BLOCKED
                result.blocked_reason = f"Call {state} before asking '{q['key']}'"
                return result

            # Treat on_hold mid-conversation as a transfer (not initial hold)
            if state == "on_hold" and idx > 0:
                log.transfer_detected()
                result.transcript.append(QATurn(
                    intent_key="__transfer__",
                    question="",
                    answer="[transferred to another department]",
                ))

            is_first = (idx == 0)
            turn = self._ask_with_retry(q["key"], q["text"], is_first_question=is_first)
            result.transcript.append(turn)

            if self._payer.call_state() in ("dropped", "unreachable"):
                log.call_dropped(q["key"])
                result.final_state = CallState.BLOCKED
                result.blocked_reason = f"Call dropped after asking '{q['key']}'"
                return result

        # ── Confirmation pass (required fields only) ───────────────────────
        log.confirm_pass_start()
        for key in required_fields:
            if key not in question_map:
                continue
            if self._payer.call_state() in ("dropped", "unreachable"):
                break
            confirm_q = question_map[key]
            confirm_text = f"Just to confirm — {confirm_q['text'].lower()}"
            turn = self._ask_with_retry(key, confirm_text)
            turn.intent_key = f"{key}__confirm"
            result.transcript.append(turn)

        result.final_state = CallState.EXTRACTING
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ask_with_retry(self, intent_key: str, question_text: str, is_first_question: bool = False) -> QATurn:
        prepared_question = self._prepare_question(question_text, is_first_question)
        log = self._logger
        retries = 0

        while retries <= MAX_RETRIES:
            log.asking(intent_key, question_text, retry=retries)
            answer = self._payer.ask(prepared_question)

            off_script = self._llm.is_off_script(question_text, answer)
            log.rep_answer(answer, off_script=off_script)

            if not off_script:
                return QATurn(
                    intent_key=intent_key,
                    question=question_text,   # log original (unmodified) for internal transcript
                    answer=answer,
                    retries=retries,
                )

            retries += 1

        # Exhausted retries — record as off-script, extraction will assign low confidence
        log.retry_exhausted(intent_key)
        return QATurn(
            intent_key=intent_key,
            question=question_text,
            answer=answer,
            retries=retries,
            off_script=True,
        )

    def _prepare_question(self, text: str, is_first_question: bool) -> str:
        """
        Encrypt the member ID before crossing the payer boundary.
        If the cleartext member ID is in the question, it is replaced.
        If this is the first question, the encrypted ID is appended so the payer receives it.
        """
        if not self._member_id:
            return text
            
        encrypted_token = PayerCrypto.encrypt_member_id(self._member_id)
        
        # If the ID was explicitly in the text, replace it
        if self._member_id in text:
            text = text.replace(self._member_id, encrypted_token)
        # Otherwise, append it to the first question so the payer knows who we are calling about
        elif is_first_question:
            text = f"{text} Member ID: {encrypted_token}"
            
        return text
