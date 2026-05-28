from dataclasses import dataclass, field
from typing import Any


@dataclass
class IVRConfig:
    """Menu tree: maps DTMF digit strings to prompt text."""
    root: str
    branches: dict[str, str] = field(default_factory=dict)  # e.g. {"1": "Hold for rep..."}


@dataclass
class ScenarioConfig:
    """
    Declarative config for one call scenario (benefits / denial / auth / ...).
    Adding a fourth scenario = one new YAML file; no code changes required.

    Fields
    ------
    name          : machine-readable identifier
    ivr_path      : ordered list of DTMF digits to reach the right department
    questions     : ordered list of (intent_key, human_readable_question) pairs
    required_fields: keys that MUST be present for a COMPLETE (not BLOCKED) result
    """
    name: str
    ivr_path: list[str]
    questions: list[dict[str, str]]   # [{"key": "coverage_active", "text": "Is the policy active?"}]
    required_fields: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)  # spare bag for future use


@dataclass
class InjectConfig:
    """Knobs for realistic failure injection inside a fixture."""
    drop_after_question: int | None = None   # drop call after N-th question
    unreachable: bool = False                # payer never picks up
    contradict: dict[str, str] | None = None # {"field": "copay", "second_answer": "$40"}
    transfer_on: str | None = None           # intent key that triggers a transfer
