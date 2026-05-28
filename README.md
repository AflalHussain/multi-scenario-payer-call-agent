# Payer Call Agent Core

A reusable, configuration-driven software core that automates insurance payer phone calls (e.g., benefits verification, denied claims, prior authorizations). 

This system is designed as a strict state machine that navigates IVR menus, conducts Q&A loops with a mock payer, and extracts structured data from messy human speech. It strictly enforces a deterministic-first architecture, reserving LLM usage only for genuine semantic ambiguity.

## Features

- **Config-Driven Scenarios**: Add new call types (like prior auth or denied claims) by simply adding a YAML file. No code changes required.
- **Deterministic State Machine**: The call lifecycle is strictly managed. Any failure (drops, contradictions, unreachable states) immediately short-circuits to a `BLOCKED` state.
- **No-Fabrication Guarantee**: The system uses deterministic reconciliation to catch contradictory answers and low-confidence extractions, ensuring it never guesses or invents a successful result.
- **Sensitive Data Boundary**: Member IDs are symmetrically encrypted (Fernet) before crossing the payer boundary, ensuring raw PHI is never exposed in transit.
- **Real-Time Observability**: Includes a `--live` terminal logger for visual state tracking and an `llm_calls.log` JSONL audit trail for debugging non-deterministic model outputs.

## Project Structure

```text
scenarios/         ← Declarative configs for call types (benefits, denial, auth)
fixtures/          ← Test cases driving the Mock Payer (clean, drop, contradict, etc.)
core/              ← The agent core (state machine, IVR, QA loop, extractor, result builder)
payer/             ← MockPayer implementation and PayerInterface
llm/               ← LLMInterface, StubLLM, and OpenRouterLLM implementations
tests/             ← Pytest suite covering happy paths and failure injections
```

## Setup & Installation

1. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **(Optional) Set up LLM API Key**:
   By default, the system uses a rule-based `StubLLM` so you can run it without API keys. To use the real LLM (we used `nvidia/nemotron-3-super-120b-a12b:free` via OpenRouter):
   ```bash
   export OPENROUTER_API_KEY="your_api_key_here"
   ```

## Running the Agent

You can run the agent using the `run.py` CLI. 

**Run a clean benefits verification call (with live terminal UI):**
```bash
python run.py --scenario scenarios/benefits_verification.yaml --fixture fixtures/benefits_clean.yaml --live
```

**Run a call that drops mid-way:**
```bash
python run.py --scenario scenarios/benefits_verification.yaml --fixture fixtures/benefits_drop.yaml --live
```

**Run a call with contradictory representative answers:**
```bash
python run.py --scenario scenarios/benefits_verification.yaml --fixture fixtures/benefits_contradiction.yaml --live
```

**Run using the real LLM instead of the stub:**
```bash
python run.py --scenario scenarios/benefits_verification.yaml --fixture fixtures/benefits_clean.yaml --llm openrouter --live
```

## Running Tests

The test suite covers golden transcripts, failure paths, and the sensitive data boundary.

```bash
python -m pytest tests/ -v
```

## Design Decisions

For a detailed breakdown of the architecture, the deterministic vs. LLM boundary, and production-hardening strategies, please read [DESIGN.md](DESIGN.md).
