# CentrAlign AI — Upgraded Autonomous Invoice Agent

A focused proof of concept demonstrating a tool-driven business agent: understand a goal, plan, call tools, observe results, recover from a temporary failure, and verify the final state.

> **Important:** The company system is simulated using local JSON files. This is not a production accounting or payment system.

## What is improved
- Optional LLM-assisted vendor extraction/planning using an OpenAI-compatible API.
- Rule-based fallback for offline/local demo use.
- Explicit tool catalog and structured execution events.
- Duplicate protection at both agent and write-tool level.
- Two-step human approval: first preview an invoice, then explicitly approve that specific invoice before writing.
- Bounded retry for a simulated temporary write failure.
- Read-after-write verification.
- Audit trail and Streamlit execution trace.
- 13 automated tests covering approval, duplicates, retries, verification failures, malformed data, vendor matching, and audit logging.

## Setup (Windows PowerShell)
```powershell
cd centralign_ai_agent_upgrade
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```
Open the local URL shown in the terminal, usually `http://localhost:8501`.

## Optional LLM planner
Copy `.env.example` to `.env`, add your API key, then restart Streamlit. The app reads environment variables; if your shell does not load `.env` automatically, either set them in PowerShell for that session:
```powershell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-4o-mini"
python -m streamlit run app.py
```
Never commit `.env` or share your API key. Without a key, the rule-based fallback is used. The LLM only extracts the vendor; it cannot authorize a write or invent a successful result.

## Demo instructions
1. Run `Process the latest invoice for ACME Supplies`. The agent should preview the invoice and stop at the approval gate.
2. Review the invoice ID, vendor, amount, currency, and due date. Check the approval box tied to that invoice, then click `Approve and execute`.
3. Enable `Simulate one temporary write failure` before running a fresh invoice to see a failed attempt, retry, successful write, and verification.
4. Run the same invoice again to demonstrate duplicate prevention.
5. Expand the execution trace and inspect the audit log.

Because the sample invoice will be added to the local records after a successful run, restore `data/company_system/invoice_records.json` to `[]` before repeating the clean demo. Do not delete your original project records unless you have a backup.

## Run tests
```powershell
python -m pytest -q
```

## Architecture
- `app.py`: Streamlit interface, invoice-specific two-step approval, event trace, demo controls.
- `agent.py`: planner, bounded orchestration, retry policy, verification flow.
- `tools.py`: local simulated company tools and audit logging.
- `data/invoices/`: sample invoices.
- `data/company_system/invoice_records.json`: simulated company records.
- `tests/`: automated behavior tests.

## Known limitations / next steps
- Invoice-specific workflow, not a general-purpose digital employee.
- Local JSON storage; not safe for concurrent or production use.
- Optional LLM call is used for vendor extraction only; execution remains constrained by code.
- No OCR/PDF extraction, real accounting API, email/browser automation, or payment execution.
- Production next steps: authenticated integrations, database transactions/idempotency, permissions, secrets management, structured model output validation, observability, and broader task evaluations.
