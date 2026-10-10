# Architecture and Design Decisions

## Execution flow
1. **Goal intake:** user enters a natural-language invoice request.
2. **Planning:** optional LLM planner extracts the vendor; fallback regex planner works without API credentials.
3. **Tool use:** find invoice → validate fields → check duplicate.
4. **Safety gate:** no new write unless user approval is checked.
5. **Execution/recovery:** write tool blocks duplicates; retry count is bounded.
6. **Verification:** read saved record and compare invoice ID, vendor, amount, currency, and due date.
7. **Evidence:** structured event trace in UI and JSON Lines audit log.

## Safety decisions
- Model output cannot grant approval.
- Model output cannot supply invoice amounts or claim tool success.
- All invoice data is loaded from local sample files.
- Tool writes independently check for duplicates.
- A temporary failure is simulated deterministically for reproducible demo testing.
- If verification fails, the agent reports failure rather than claiming success.

## Trade-offs
- **Local JSON over database:** easy to run and inspect for a prototype; unsuitable for concurrency/production.
- **Bounded tools over arbitrary code execution:** safer and easier to evaluate; limited generality.
- **Optional LLM with fallback:** demonstrates a model-assisted planning layer without making the app unusable when no API key is configured.
- **Read-after-write verification:** adds confidence that a reported success reflects persisted state.

## Not implemented
No live company APIs, payments, browser control, OCR, general-purpose dynamic planning, distributed locking, or production security controls.
