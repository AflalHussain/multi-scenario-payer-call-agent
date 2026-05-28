from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExtractionResult:
    value: str | None          # extracted value, or None if uninterpretable
    confidence: float          # 0.0 – 1.0
    raw_reasoning: str = ""    # model's chain-of-thought (debug only)


class LLMInterface(ABC):
    """
    Seam for all LLM calls in the agent.

    DESIGN NOTE: Only two operations reach an LLM:
      1. extract() — parse a messy free-text rep answer into a typed value
      2. is_off_script() — decide if an answer is too ambiguous to parse deterministically

    Everything else (IVR nav, known-question routing, state transitions)
    is deterministic code. See DESIGN.md §"LLM vs deterministic boundary".
    """

    @abstractmethod
    def extract(self, question: str, answer: str, field_type: str, nullable: bool) -> ExtractionResult:
        """
        Given a question and the rep's raw answer, extract a typed value.

        Parameters
        ----------
        question   : the question that was asked (for context)
        answer     : raw free-text rep answer
        field_type : hint for the expected type ("boolean", "currency", "integer", "text")
        """

    @abstractmethod
    def is_off_script(self, question: str, answer: str) -> bool:
        """
        Return True if the answer is so unexpected that extraction should be skipped
        and the question retried (or escalated to human).
        """
