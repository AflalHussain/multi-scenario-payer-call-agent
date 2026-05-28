"""
LLM stub — runs without a real API key.

To wire a real model, subclass LLMInterface and swap this out.
The prompts below document exactly what would be sent to the model.

Model routing (see DESIGN.md):
  - extract()       → fast/cheap model (e.g. claude-haiku) — high volume, structured output
  - is_off_script() → same fast model — binary classification, latency-sensitive
"""
import re
from .interface import LLMInterface, ExtractionResult

# ---- Prompt templates (documented here even in stub mode) ----------------

EXTRACT_PROMPT = """You are extracting a single structured value from a payer representative's answer.

Question asked: {question}
Representative's answer: {answer}
Expected field type: {field_type}

Rules:
- Return ONLY a JSON object: {{"value": <extracted value or null>, "confidence": <0.0-1.0>}}
- If the answer is ambiguous or contradictory, set value to null and confidence below 0.5
- For "boolean": true/false only
- For "currency": numeric string like "20"
- For "integer": numeric string
- For "text": cleaned prose, no filler words
- Never invent a value that wasn't stated
"""

OFF_SCRIPT_PROMPT = """Does this insurance representative answer make sense as a response to this benefits/claims question?
Question: {question}

Answer: {answer}

Reply with exactly one word: YES or NO
"""

# --------------------------------------------------------------------------


class StubLLM(LLMInterface):
    """
    Rule-based stub that mimics what the LLM would do.
    Replace with a real LLM client for production.
    """

    def extract(self, question: str, answer: str, field_type: str) -> ExtractionResult:
        # Log the prompt that would be sent (useful during development)
        _ = EXTRACT_PROMPT.format(question=question, answer=answer, field_type=field_type)

        answer_lower = answer.lower().strip()

        if field_type == "boolean":
            if any(w in answer_lower for w in ("yes", "active", "valid", "covered", "yeah")):
                return ExtractionResult(value="true", confidence=0.9)
            if any(w in answer_lower for w in ("no", "inactive", "not covered", "denied")):
                return ExtractionResult(value="false", confidence=0.9)
            return ExtractionResult(value=None, confidence=0.3)

        if field_type == "currency":
            match = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", answer)
            if match:
                return ExtractionResult(value=match.group(1), confidence=0.85)
            # Handle written-out numbers (real LLM handles these natively)
            word_to_num = {
                "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
                "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
                "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
                "fifteen": "15", "twenty": "20",
                "twenty-five": "25", "thirty": "30", "forty": "40", "fifty": "50",
            }
            for word, num in word_to_num.items():
                if word in answer_lower:
                    return ExtractionResult(value=num, confidence=0.75)
            return ExtractionResult(value=None, confidence=0.2)

        if field_type == "integer":
            match = re.search(r"\b(\d+)\b", answer)
            if match:
                return ExtractionResult(value=match.group(1), confidence=0.85)
            return ExtractionResult(value=None, confidence=0.2)

        # Default: text — return cleaned answer
        cleaned = re.sub(r"\s+", " ", answer).strip()
        confidence = 0.7 if cleaned else 0.0
        return ExtractionResult(value=cleaned or None, confidence=confidence)

    def is_off_script(self, question: str, answer: str) -> bool:
        _ = OFF_SCRIPT_PROMPT.format(question=question, answer=answer)  # log prompt
        off_script_signals = (
            "i don't understand",
            "wrong department",
            "cannot help",
            "system is down",
        )
        return any(s in answer.lower() for s in off_script_signals)
