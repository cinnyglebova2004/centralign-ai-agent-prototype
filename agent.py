"""Tool-driven invoice agent with optional LLM planning and deterministic fallback."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Callable

from tools import (
    find_latest_invoice, read_invoice, lookup_record, write_record,
    verify_record, append_audit, ToolError
)

TOOL_SCHEMAS = {
    "find_latest_invoice": {"description": "Find the latest invoice for a vendor", "args": {"vendor": "string"}},
    "read_invoice": {"description": "Read and validate an invoice file", "args": {"invoice_id": "string"}},
    "lookup_record": {"description": "Check whether an invoice ID already exists in company records", "args": {"invoice_id": "string"}},
    "write_record": {"description": "Write an approved, non-duplicate invoice record", "args": {"invoice": "object"}},
    "verify_record": {"description": "Read a record back and compare it with the intended invoice", "args": {"invoice_id": "string", "expected": "object"}},
}

@dataclass
class Event:
    step: int
    kind: str
    message: str
    details: dict[str, Any] | None = None

@dataclass
class RunResult:
    status: str
    summary: str
    plan: list[str]
    events: list[dict[str, Any]]
    result: dict[str, Any] | None = None
    approval_required: bool = False

class Planner:
    """LLM planner when OPENAI_API_KEY is present; safe deterministic fallback otherwise."""
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def plan(self, request: str) -> dict[str, Any]:
        if self.api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self.api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content":
                         "You plan a safe invoice-processing task. Return JSON only with keys "
                         "'vendor' (string) and 'intent' ('process_invoice'). Do not invent invoice IDs, "
                         "amounts, approvals, or claim actions are done. If no vendor is clear, use empty string."},
                        {"role": "user", "content": request},
                    ],
                )
                obj = json.loads(response.choices[0].message.content or "{}")
                vendor = str(obj.get("vendor", "")).strip()
                if vendor:
                    return {"vendor": vendor, "source": "llm", "intent": "process_invoice"}
            except Exception:
                # A model/API failure must not block the bounded fallback.
                pass
        vendor = self._extract_vendor(request)
        return {"vendor": vendor, "source": "rule_fallback", "intent": "process_invoice"}

    @staticmethod
    def _extract_vendor(request: str) -> str:
        patterns = [
            r"(?:for|from|vendor(?:\s+is)?|supplier(?:\s+is)?)\s+['\"]?([A-Za-z][A-Za-z0-9 &._-]*?)['\"]?(?:\s+invoice|\s+invoices|\s+and\b|[,.!?]|$)",
            r"\b(?:process|handle|pay|check)\s+([A-Za-z][A-Za-z0-9 &._-]*?)\s+invoice\b",
        ]
        for pat in patterns:
            match = re.search(pat, request, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .,!?:;'\"")
                if value.lower() not in {"the", "an", "a", "latest", "this"}:
                    return value
        # Common natural-language phrasing: "process ACME Supplies invoice"
        match = re.search(r"\b(?:process|handle|check)\s+(.+?)\s+invoice\b", request, re.IGNORECASE)
        return match.group(1).strip(" .,!?:;'\"") if match else ""

class AutonomousInvoiceAgent:
    def __init__(self, max_retries: int = 2):
        self.planner = Planner()
        self.max_retries = max(1, min(int(max_retries), 3))
        self.events: list[Event] = []
        self._step = 0

    def _event(self, kind: str, message: str, details: dict[str, Any] | None = None):
        self._step += 1
        self.events.append(Event(self._step, kind, message, details))

    def run(self, request: str, approved: bool = False, simulate_failure: bool = False) -> RunResult:
        self.events, self._step = [], 0
        plan_obj = self.planner.plan(request)
        vendor = plan_obj.get("vendor", "")
        plan = [
            "Understand request and identify vendor",
            "Find and validate the latest matching invoice",
            "Check for an existing record",
            "Request approval before any new write",
            "Write with bounded retry and verify by reading back",
        ]
        self._event("plan", f"Planner selected {plan_obj['source']} and identified vendor: {vendor or '(not identified)'}",
                    {"planner": plan_obj["source"], "vendor": vendor, "available_tools": list(TOOL_SCHEMAS)})
        if not vendor:
            return self._finish("needs_input", "I couldn't identify the vendor. Include a vendor name, e.g. 'Process the latest invoice for ACME Supplies'.", plan)

        try:
            found = find_latest_invoice(vendor)
            self._event("tool", "find_latest_invoice completed", {"vendor": vendor, "invoice_id": found.get("invoice_id")})
            invoice = read_invoice(found["invoice_id"])
            self._event("observation", "Invoice fields validated", {"invoice_id": invoice["invoice_id"], "amount": invoice["amount"], "currency": invoice["currency"]})
            existing = lookup_record(invoice["invoice_id"])
            self._event("tool", "lookup_record completed", {"invoice_id": invoice["invoice_id"], "exists": existing is not None})
        except (ToolError, KeyError, ValueError) as exc:
            self._event("error", str(exc))
            append_audit({"status": "failed", "request": request, "error": str(exc), "events": [asdict(e) for e in self.events]})
            return self._finish("failed", f"Could not safely process invoice: {exc}", plan)

        if existing:
            self._event("safety", "Duplicate prevented; no write performed", {"invoice_id": invoice["invoice_id"]})
            append_audit({"status": "duplicate", "request": request, "invoice_id": invoice["invoice_id"], "events": [asdict(e) for e in self.events]})
            return self._finish("duplicate", f"Invoice {invoice['invoice_id']} already exists. No duplicate record was created.", plan, existing)

        if not approved:
            self._event("approval", "Approval required before writing", {"invoice_id": invoice["invoice_id"], "amount": invoice["amount"], "currency": invoice["currency"]})
            return self._finish("approval_required", f"Approval is required before writing invoice {invoice['invoice_id']} ({invoice['currency']} {invoice['amount']:,.2f}).", plan, invoice, True)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._event("action", f"Write attempt {attempt} started", {"attempt": attempt})
                write_record(invoice, simulate_failure=(simulate_failure and attempt == 1))
                self._event("observation", f"Write attempt {attempt} succeeded", {"attempt": attempt})
                last_error = None
                break
            except ToolError as exc:
                last_error = str(exc)
                self._event("retry" if attempt < self.max_retries else "error",
                            f"Write attempt {attempt} failed: {exc}",
                            {"attempt": attempt, "will_retry": attempt < self.max_retries})
        if last_error:
            append_audit({"status": "failed", "request": request, "invoice_id": invoice["invoice_id"], "error": last_error, "events": [asdict(e) for e in self.events]})
            return self._finish("failed", f"Write failed after {self.max_retries} attempt(s): {last_error}", plan, invoice)

        try:
            verified = verify_record(invoice["invoice_id"], invoice)
            self._event("verification", "Read-after-write verification passed", {"invoice_id": invoice["invoice_id"], "verified": True})
        except ToolError as exc:
            self._event("error", f"Verification failed: {exc}")
            append_audit({"status": "verification_failed", "request": request, "invoice_id": invoice["invoice_id"], "error": str(exc), "events": [asdict(e) for e in self.events]})
            return self._finish("verification_failed", f"The write may have occurred, but verification failed: {exc}", plan, invoice)

        append_audit({"status": "completed", "request": request, "invoice_id": invoice["invoice_id"], "events": [asdict(e) for e in self.events]})
        return self._finish("completed", f"Invoice {invoice['invoice_id']} was saved and verified successfully.", plan, verified)

    def _finish(self, status, summary, plan, result=None, approval_required=False):
        return RunResult(status, summary, plan, [asdict(e) for e in self.events], result, approval_required)
