"""
Real LLM implementation via OpenRouter (google/gemma-4-31b-it:free).

Reasoning is enabled on every call so the model's chain-of-thought is
captured in ExtractionResult.raw_reasoning for debugging.

Usage
-----
    from llm.openrouter import OpenRouterLLM

    llm = OpenRouterLLM(api_key="sk-or-...")
    result = llm.extract(question, answer, field_type)

Environment
-----------
    Set OPENROUTER_API_KEY in the environment to avoid passing it explicitly:

        export OPENROUTER_API_KEY="sk-or-..."
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any

import requests

from .interface import ExtractionResult, LLMInterface

# ── constants ────────────────────────────────────────────────────────────────

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"#"liquid/lfm-2.5-1.2b-instruct:free" #"google/gemma-4-31b-it:free" # 
_REASONING = {"enabled": False}

# ── prompt templates (mirrors stub.py for easy comparison) ───────────────────

EXTRACT_PROMPT = """You are a strict data extraction assistant. Extract a single structured value from the payer representative's answer based on the question asked.

Question asked: {question}
Representative's answer: {answer}
Expected field type: {field_type} {nullable_str}

STRICT RULES:
1. Return ONLY a valid JSON object: {{"value": <extracted_value>, "confidence": <float 0.0-1.0>}}
2. If the answer is ambiguous, dodges the question, or contains contradictions, set "value" to null and "confidence" below 0.5.
3. or if answer is valid and a field type is not applicable set "value" to N/A and "confidence" to 0.9.
4. Type-specific formatting for "value":
   - "boolean": Use JSON boolean `true` or `false` for the question given (not strings).
   - "currency": Use a numeric string without currency symbols (e.g., "20" or "20.00" for "twenty dollars" or "$20").
   - "integer": Use a numeric string (e.g., "30") or N/A if not applicable.
   - "text": Extract the exact, concise relevant phrase from the answer. Do not paraphrase.
5. Never invent, infer, or assume a value that was not explicitly stated.
"""

OFF_SCRIPT_PROMPT = """Does this insurance representative answer make sense as a response to this benefits/claims question?
Question: {question}

Answer: {answer}

Reply with exactly one word: YES or NO
"""


# ── helper ───────────────────────────────────────────────────────────────────
    
def _extract_reasoning(message: dict[str, Any]) -> str:
    """Pull the chain-of-thought text out of a response message."""
    details = message.get("reasoning_details") or []
    parts = [
        block.get("thinking", "")
        for block in details
        if isinstance(block, dict) and block.get("thinking")
    ]
    # Some models surface reasoning in a top-level "reasoning" field instead
    if not parts and message.get("reasoning"):
        parts = [message["reasoning"]]
    return "\n".join(parts).strip()


# ── main class ───────────────────────────────────────────────────────────────

class OpenRouterLLM(LLMInterface):
    """
    Production LLM client backed by OpenRouter.

    Parameters
    ----------
    api_key : str | None
        OpenRouter API key.  Falls back to the ``OPENROUTER_API_KEY``
        environment variable if not provided.
    model : str
        OpenRouter model slug.  Defaults to ``google/gemma-4-31b-it:free``.
    timeout : int
        Request timeout in seconds (default 60).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OpenRouter API key is required. "
                "Pass api_key= or set the OPENROUTER_API_KEY environment variable."
            )
        self._model = model
        self._timeout = timeout

    # ── private helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Single OpenRouter call.  Returns the raw assistant message dict
        (including ``reasoning_details`` when the model provides it).
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "reasoning": _REASONING,
        }
        resp = requests.post(
            _API_URL,
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        response_json = resp.json()
        assistant_message = response_json["choices"][0]["message"]
        
        self._log_call(payload, response_json)
        
        return assistant_message

    def _log_call(self, payload: dict[str, Any], response: dict[str, Any]) -> None:
        """Log the LLM request and response to a file."""
        log_file = "llm_calls.log"
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "request": payload,
            "response": response
        }
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            # Fail silently if logging fails to avoid breaking the agent
            pass

    # ── public interface ─────────────────────────────────────────────────────

    def extract(self, question: str, answer: str, field_type: str, nullable: bool = False) -> ExtractionResult:
        """
        Ask the model to extract a typed value from the rep's raw answer.

        Uses a two-turn exchange so the model can reason, then commit to a
        final JSON answer — mirroring the pattern in the docstring example.
        """
        nullable_str = " or N/A" if nullable else ""
        prompt = EXTRACT_PROMPT.format(
            question=question, answer=answer, field_type=field_type, nullable_str=nullable_str
        )

        # ── turn 1: let the model reason ──────────────────────────────────
        turn1_messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt}
        ]
        assistant_msg = self._chat(turn1_messages)
        reasoning = _extract_reasoning(assistant_msg)

        # ── turn 2: ask it to commit if the first reply isn't pure JSON ──
        first_content = (assistant_msg.get("content") or "").strip()
        json_match = re.search(r"\{.*\}", first_content, re.DOTALL)

        if not json_match:
            # Model reasoned but didn't output JSON yet — nudge it
            turn2_messages: list[dict[str, Any]] = [
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "content": assistant_msg.get("content"),
                    "reasoning_details": assistant_msg.get("reasoning_details"),
                },
                {
                    "role": "user",
                    "content": (
                        "Now output ONLY the JSON object with 'value' and 'confidence'. "
                        "No other text."
                    ),
                },
            ]
            assistant_msg2 = self._chat(turn2_messages)
            if assistant_msg2.get("reasoning"):
                reasoning += "\n" + _extract_reasoning(assistant_msg2)
            first_content = (assistant_msg2.get("content") or "").strip()
            json_match = re.search(r"\{.*\}", first_content, re.DOTALL)

        # ── parse JSON ──────────────────────────────────────────────────
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                raw_value = parsed.get("value")
                confidence = float(parsed.get("confidence", 0.5))
                # Normalise booleans to string "true"/"false"
                if isinstance(raw_value, bool):
                    raw_value = str(raw_value).lower()
                elif raw_value is not None:
                    raw_value = str(raw_value)
                return ExtractionResult(
                    value=raw_value,
                    confidence=max(0.0, min(1.0, confidence)),
                    raw_reasoning=reasoning,
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: couldn't parse — return low-confidence null
        return ExtractionResult(value=None, confidence=0.1, raw_reasoning=reasoning)

    def is_off_script(self, question: str, answer: str) -> bool:
        """
        Return True when the rep's answer is too unexpected to parse normally.

        Uses a single-turn call; no second turn needed for a YES/NO decision.
        """
        prompt = OFF_SCRIPT_PROMPT.format(question=question, answer=answer)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        assistant_msg = self._chat(messages)
        reply = (assistant_msg.get("content") or "").strip().upper()
        # Treat anything that isn't a clear YES as on-script (safe default)
        return reply.startswith("NO")
