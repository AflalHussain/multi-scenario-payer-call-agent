# DESIGN.md

## Architecture overview

One agent core (`core/agent.py`) driven by declarative scenario configs (YAML).
Adding a new scenario requires only a new YAML file no code changes.

```
scenarios/         ← one file per call type
fixtures/          ← one file per test case (drives the mock payer)
core/agent.py      ← state machine orchestrator
core/ivr_navigator ← deterministic IVR navigation
core/qa_loop       ← question/answer loop, retry, masking
core/extractor     ← LLM-based answer extraction
core/extractor     ← deterministic reconciliation + confidence
core/result_builder← assembles CallResult, enforces no-fabrication
payer/             ← MockPayer (fixture-driven) behind PayerInterface
llm/               ← LLMInterface + StubLLM (swap for real model)
models/            ← CallState, ScenarioConfig, CallResult
```

## State machine

```
INITIALIZING → DIALING → NAVIGATING_IVR → WAITING_FOR_REP
    → ASKING → EXTRACTING → COMPLETE | BLOCKED
```

Any failure at any state short-circuits directly to BLOCKED.
The agent never advances past EXTRACTING without a high-confidence result.

## LLM vs deterministic boundary

| Step | Approach | Reason |
|---|---|---|
| IVR navigation | Deterministic | Digits are known from config; no ambiguity |
| Question routing | Deterministic | Question list is fixed by scenario |
| Off-script detection | LLM (fast model) | Binary: "does this answer make sense?" |
| Answer extraction | LLM (fast model) | Free-text → typed value requires language understanding |
| Contradiction detection | Deterministic | Simple value comparison |
| Confidence scoring | Deterministic | Mean of per-field scores |
| Result assembly | Deterministic | Rule-based thresholds |

**Model routing**: Both LLM calls route to a fast/cheap model (e.g. `claude-haiku`).
Phone calls are latency-sensitive and these calls are high-volume.
A capable model is not needed — the tasks are structured extraction and binary classification.

## Sensitive data boundary

The patient's member ID is encrypted in `core/qa_loop.py` before any call to
`payer.ask()`. The real ID is replaced with a symmetric encrypted token (e.g., `[ENC:...]`) using Fernet encryption. The mock payer (and any real telephony integration) receives the encrypted token and decrypts it on their end, ensuring the raw member ID is never passed in the clear across this boundary.

This is documented here rather than left implicit in the code.

## Observability & Debugging

LLMs are non-deterministic, making them notoriously hard to debug. We split observability into two distinct layers:
1. **Developer Experience (DX):** A `LiveLogger` provides real-time, state-machine-aware terminal output (color-coded, typewriter effects) when running with the `--live` flag. It defaults to a `SILENT` singleton during tests to ensure zero overhead.
2. **LLM Auditability:** Every LLM request and raw response is appended to `llm_calls.log` in JSONL format. If the agent fails an extraction, we have an exact paper trail of the prompt and the model's raw output.
3. **Structured Transcripts:** The final `CallResult` includes the exact turn-by-turn transcript, including retries and off-script flags, rather than just the extracted data.

## What I deferred

- **Real LLM integration**: `StubLLM` covers the interface. Wiring a real client
  is a one-file change in `llm/`.
- **IVR re-navigation after transfer**: current code optimistically continues;
  production would re-enter the IVR loop for the new department.
- **Retry with backoff on unreachable**: currently a single attempt. Production
  would retry with exponential backoff and a configurable max.
- **Production Observability**: We implemented local audit logging (`llm_calls.log`), but production requires distributed tracing (e.g., OpenTelemetry/LangSmith) for latency/cost tracking, and metrics/alerting (e.g., Datadog) for extraction confidence drops.
- **Scenario template enhancement: nullable fields**: he scenario schema was extended to support fields that may legitimately return "N/A" in addition to their primary typed value (string, integer, boolean, etc.).

## Where AI tooling shaped this solution

AI assistance (an agentic coding assistant) was used throughout this project. I want to be honest and specific about where it contributed, because I believe transparency here is itself part of the judgment:

**Requirement Decomposition:** I used AI to help me break down the specification document into discrete deliverables (state machine, interfaces, fixture shapes, failure nodes) and to identify implicit constraints such as the sensitive data boundary before writing any code. The architectural strategy of separating "what to ask" (scenario YAML) from "how to call" (agent core) came out of that initial conversation.

**Scaffolding:** The directory structure, interface definitions (`PayerInterface`, `LLMInterface`, `CallResult`), and the initial pass of the state machine skeleton were generated with AI assistance, shaped by my decisions on abstraction boundaries (e.g., keeping `MockPayer` behind a strict interface, having one core drive all scenarios).

**Implementation Logic:** Specific modules — the `QALoop` retry logic, the `Extractor` field parsing, the `ResultBuilder`'s no-fabrication guards, and the Fernet-based `PayerCrypto` — were implemented with significant AI assistance. In each case, I specified the requirements and constraints (e.g., "if confidence is below 0.8 on any required field, block the result"), reviewed the output, and steered corrections.

**Observability Features:** The `LiveLogger` and the `llm_calls.log` JSONL audit trail were ideas I directed and AI executed. These were deliberate design choices I made to make LLM debugging tractable.

**Debugging & Fixes:** Test failures (e.g., the `StubLLM.is_off_script` signature mismatch after the interface was updated in `openrouter.py`, the `MockPayer` question counter needing to be per-intent rather than global) were diagnosed and fixed with AI assistance after I identified the symptoms from test output.

**

**What remained mine:** The architectural decisions — which steps use an LLM vs. deterministic logic, how the state machine is structured, the choice to use encryption rather than masking for the member ID, the constraint that the result builder can never fabricate a success are all judgments I made and guided. The AI was my implementation pair, not the architect.

I am able to explain every line of this codebase, walk through its design trade-offs, and reason about how I would extend or harden it for production use.
