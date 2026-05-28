"""
LiveLogger — real-time conversational output for the payer call agent.

When enabled (--live flag), prints each stage of the call as it happens:
  - State machine transitions with timestamps
  - IVR navigation (DTMF keypresses + menu prompts)
  - Questions typed out character-by-character
  - Rep answers appearing with a natural pause
  - Per-field extraction results
  - Final pass/block verdict

When disabled (default), this is a no-op with zero overhead.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime


# ── ANSI colour helpers ───────────────────────────────────────────────────────

class _C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Semantic colours
    CYAN    = "\033[96m"   # agent / system messages
    YELLOW  = "\033[93m"   # IVR / automated prompts
    GREEN   = "\033[92m"   # success / complete
    RED     = "\033[91m"   # error / blocked
    MAGENTA = "\033[95m"   # LLM extraction
    WHITE   = "\033[97m"   # rep speech
    BLUE    = "\033[94m"   # state transitions
    ORANGE  = "\033[33m"   # warnings / off-script


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _print(colour: str, icon: str, label: str, msg: str = "", dim_msg: bool = False) -> None:
    ts     = f"{_C.DIM}[{_ts()}]{_C.RESET}"
    header = f"{colour}{_C.BOLD}{icon} {label}{_C.RESET}"
    body   = f"  {_C.DIM}{msg}{_C.RESET}" if dim_msg else f"  {msg}" if msg else ""
    print(f"{ts} {header}{body}", flush=True)


def _typewrite(text: str, delay: float = 0.028) -> None:
    """Print text character by character to simulate typing."""
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _divider(char: str = "─", width: int = 60) -> None:
    print(f"{_C.DIM}{char * width}{_C.RESET}", flush=True)


# ── Public logger class ───────────────────────────────────────────────────────

class LiveLogger:
    """
    Drop-in observer.  Pass an instance into PayerCallAgent; if enabled=False
    every method is a no-op so production code is unaffected.

    Delay profile (seconds):
        dial_delay      – pause before "calling" completes
        ivr_delay       – pause between each DTMF press
        question_delay  – pause before the agent speaks
        answer_delay    – pause simulating rep thinking before reply
        extract_delay   – pause while "processing" each field
        result_delay    – pause before final summary
    """

    def __init__(
        self,
        enabled: bool = False,
        dial_delay:     float = 1.5,
        ivr_delay:      float = 0.8,
        question_delay: float = 0.6,
        answer_delay:   float = 1.2,
        extract_delay:  float = 0.4,
        result_delay:   float = 0.8,
    ) -> None:
        self.enabled        = enabled
        self.dial_delay     = dial_delay
        self.ivr_delay      = ivr_delay
        self.question_delay = question_delay
        self.answer_delay   = answer_delay
        self.extract_delay  = extract_delay
        self.result_delay   = result_delay
        self._turn          = 0

    # ── Call lifecycle ────────────────────────────────────────────────────────

    def call_start(self, scenario: str, fixture: str) -> None:
        if not self.enabled:
            return
        _divider("═")
        print(
            f"{_C.BOLD}{_C.CYAN}  📞  PAYER CALL AGENT  —  live session{_C.RESET}",
            flush=True,
        )
        print(
            f"{_C.DIM}  scenario : {scenario}"
            f"\n  fixture  : {fixture}{_C.RESET}",
            flush=True,
        )
        _divider("═")
        print(flush=True)

    def state_change(self, state: str, detail: str = "") -> None:
        if not self.enabled:
            return
        icons = {
            "INITIALIZING":   "🔧",
            "DIALING":        "📡",
            "NAVIGATING_IVR": "🎛️ ",
            "WAITING_FOR_REP":"⏳",
            "ASKING":         "💬",
            "EXTRACTING":     "🔍",
            "COMPLETE":       "✅",
            "BLOCKED":        "🚫",
        }
        icon  = icons.get(state, "▶ ")
        extra = f" — {detail}" if detail else ""
        _print(_C.BLUE, icon, f"STATE → {state}{extra}")

        # State-specific delays to create a sense of real time passing
        delays = {
            "DIALING":        self.dial_delay,
            "NAVIGATING_IVR": 0.3,
            "WAITING_FOR_REP": self.ivr_delay,
        }
        _pause(delays.get(state, 0))

    def call_unreachable(self) -> None:
        if not self.enabled:
            return
        _print(_C.RED, "❌", "PAYER UNREACHABLE", "No answer — call cannot be placed.")
        _pause(0.5)

    # ── IVR navigation ────────────────────────────────────────────────────────

    def ivr_prompt(self, prompt: str) -> None:
        if not self.enabled:
            return
        _print(_C.YELLOW, "🤖", "IVR", f'"{prompt}"')
        _pause(self.ivr_delay * 0.5)

    def ivr_press(self, digit: str) -> None:
        if not self.enabled:
            return
        _print(_C.CYAN, "☎️ ", "AGENT presses", f"[ {digit} ]")
        _pause(self.ivr_delay)

    def on_hold(self) -> None:
        if not self.enabled:
            return
        _print(_C.YELLOW, "🎵", "ON HOLD", "Waiting for representative…")
        _pause(self.ivr_delay)

    # ── Q & A turns ────────────────────────────────────────────────────────────

    def asking(self, intent: str, question: str, retry: int = 0) -> None:
        if not self.enabled:
            return
        self._turn += 1
        print(flush=True)
        _divider()
        retry_tag = f"  (retry {retry})" if retry else ""
        intent_tag = f"{_C.DIM}[{intent}]{_C.RESET}"
        print(
            f"{_C.DIM}[{_ts()}]{_C.RESET} "
            f"{_C.CYAN}{_C.BOLD}🧑‍💼 AGENT{_C.RESET} {intent_tag}{_C.DIM}{retry_tag}{_C.RESET}",
            flush=True,
        )
        _pause(self.question_delay)
        sys.stdout.write(f"  {_C.CYAN}\"")
        _typewrite(question, delay=0.025)
        sys.stdout.write(f"{_C.RESET}")
        _pause(self.answer_delay)

    def rep_answer(self, answer: str, off_script: bool = False) -> None:
        if not self.enabled:
            return
        colour = _C.ORANGE if off_script else _C.WHITE
        label  = "REP (off-script ⚠️ )" if off_script else "REP"
        print(
            f"{_C.DIM}[{_ts()}]{_C.RESET} "
            f"{colour}{_C.BOLD}👤 {label}{_C.RESET}",
            flush=True,
        )
        sys.stdout.write(f"  {colour}\"")
        _typewrite(answer if answer else "(silence)", delay=0.018)
        sys.stdout.write(f"{_C.RESET}")

    def retry_exhausted(self, intent: str) -> None:
        if not self.enabled:
            return
        _print(_C.ORANGE, "⚠️ ", "RETRY EXHAUSTED",
               f"'{intent}' still off-script — marking low confidence.")

    def call_dropped(self, after: str) -> None:
        if not self.enabled:
            return
        print(flush=True)
        _print(_C.RED, "📵", "CALL DROPPED", f"after '{after}'")

    def transfer_detected(self) -> None:
        if not self.enabled:
            return
        _print(_C.YELLOW, "🔀", "TRANSFERRED", "Rep is moving to another department.")
        _pause(self.ivr_delay)

    # ── Confirmation pass ─────────────────────────────────────────────────────

    def confirm_pass_start(self) -> None:
        if not self.enabled:
            return
        print(flush=True)
        _print(_C.DIM, "🔁", "CONFIRMATION PASS", "Re-asking required fields…", dim_msg=False)

    # ── Extraction ────────────────────────────────────────────────────────────

    def extract_start(self) -> None:
        if not self.enabled:
            return
        print(flush=True)
        _divider("═")
        _print(_C.MAGENTA, "🔍", "EXTRACTING  structured data from transcript…")
        _pause(self.extract_delay)

    def field_extracted(
        self, key: str, value: str | None, confidence: float, off_script: bool = False
    ) -> None:
        if not self.enabled:
            return
        if value is None:
            status = f"{_C.RED}null{_C.RESET}"
            icon   = "✗"
            colour = _C.RED
        else:
            status = f"{_C.GREEN}{value!r}{_C.RESET}"
            icon   = "✓"
            colour = _C.GREEN

        conf_bar = _confidence_bar(confidence)
        os_tag   = f"  {_C.ORANGE}(off-script){_C.RESET}" if off_script else ""
        print(
            f"  {colour}{icon}{_C.RESET}  "
            f"{_C.BOLD}{key:<25}{_C.RESET}"
            f"{status:<30}"
            f" conf {conf_bar} {confidence:.2f}"
            f"{os_tag}",
            flush=True,
        )
        _pause(self.extract_delay * 0.6)

    def contradiction_found(self, field: str, first: str, second: str) -> None:
        if not self.enabled:
            return
        _print(_C.RED, "⚡", "CONTRADICTION",
               f"'{field}' said {first!r} then {second!r}")

    # ── Final verdict ─────────────────────────────────────────────────────────

    def final_result(self, status: str, confidence: float, reason: str | None) -> None:
        if not self.enabled:
            return
        print(flush=True)
        _pause(self.result_delay)
        _divider("═")
        if status == "complete":
            _print(_C.GREEN, "✅", f"RESULT: COMPLETE",
                   f"overall confidence {confidence:.2f}")
        else:
            _print(_C.RED, "🚫", f"RESULT: BLOCKED",
                   f"reason: {reason or 'unknown'}")
        _divider("═")
        print(flush=True)


# ── Shared no-op singleton (used when live mode is off) ───────────────────────

SILENT = LiveLogger(enabled=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confidence_bar(conf: float, width: int = 8) -> str:
    filled = round(conf * width)
    bar    = "█" * filled + "░" * (width - filled)
    if conf >= 0.7:
        colour = _C.GREEN
    elif conf >= 0.5:
        colour = _C.YELLOW
    else:
        colour = _C.RED
    return f"{colour}{bar}{_C.RESET}"
