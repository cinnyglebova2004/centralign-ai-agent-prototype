
# CentrAlign AI: Autonomous Invoice Task Worker

A bounded proof of concept for the AI employee problem statement. It finds the newest invoice for a named vendor, extracts structured fields, checks for duplicates, writes to a simulated company system, retries a transient failure, verifies the saved record, and produces an audit log.

## Run locally

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Demo task

`Find the latest invoice from Acme Supplies, record its amount and due date in the internal system, and verify it.`

Try enabling **Simulate one temporary tool failure** to demonstrate recovery. The system should retry and only report success after read-after-write verification.

## Architecture

- `app.py`: simple UI for submitting a goal and viewing evidence.
- `agent.py`: task interpretation, planning, control flow, validation, approval gate, retries and verification.
- `tools.py`: tool interfaces for searching and reading invoice files, reading/writing the simulated internal system, and appending audit events.
- `data/invoices/`: sample source documents represented as JSON.
- `data/company_system/`: simulated destination system.
- `logs/audit.jsonl`: append-only execution events.

## Key design decisions

1. **Narrow scope:** one complete workflow is more credible than pretending to support every enterprise task.
2. **Tool separation:** the agent decides the sequence; tool functions perform bounded operations.
3. **Duplicate prevention:** an invoice ID is checked before a write, and the destination tool blocks duplicates too.
4. **Failure recovery:** a transient write failure can be retried a limited number of times.
5. **Verification:** success is reported only after reading the record back and comparing key fields.
6. **Human approval:** the UI exposes an approval gate before writing. The UI requires the user to check an explicit approval box before writing. In production, the approval should bind to a displayed, immutable payload and be recorded with the approver identity.
7. **Safe sandbox:** all operations are local and use sample data. No real company credentials or third-party systems are accessed.

## Limitations

- The planner is intentionally bounded and uses lightweight phrase matching rather than a general LLM planner.
- Invoices are structured JSON rather than OCR-extracted PDFs.
- The company system is a local JSON file, not a real enterprise API.
- The prototype supports invoice recording, not arbitrary desktop tasks.
- The demo approval flow should be separated into plan/approval/commit for production use.

## What I would build next

- Add an LLM planner with strict structured output and a tool allowlist.
- Add PDF parsing/OCR and confidence checks for extracted fields.
- Separate approval from execution so no write happens until a user confirms the exact payload.
- Add unit and integration tests, structured telemetry, idempotency keys, and role-based permissions.
- Add browser/API connectors behind the same tool interface and evaluate on a fixed task suite.

## Evaluation checklist

- [x] Require an explicit approval checkbox before writing.
- [x] Understand a natural-language goal within the supported task.
- [x] Plan multiple steps.
- [x] Select and call tools.
- [x] Observe tool results.
- [x] Retry a transient failure.
- [x] Detect duplicate records.
- [x] Verify saved data.
- [x] Return evidence and an audit log.
- [ ] General-purpose LLM planning.
- [ ] Real browser/desktop automation.
