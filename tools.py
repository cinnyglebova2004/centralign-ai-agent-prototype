"""Bounded local tools for the CentrAlign invoice-agent demo.

The company system is intentionally simulated with JSON files. Never use this demo
as a real payment or accounting integration without authentication, authorization,
transactional writes, and security review.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "company_system"
INVOICE_DIR = ROOT / "data" / "invoices"
LOG_DIR = ROOT / "logs"
RECORDS_PATH = DATA_DIR / "invoice_records.json"
AUDIT_PATH = LOG_DIR / "audit.jsonl"

class ToolError(RuntimeError):
    pass

def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ToolError(f"Required data file not found: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        raise ToolError(f"Invalid JSON in {path.name}: {exc}")

def find_latest_invoice(vendor: str) -> dict[str, Any]:
    if not vendor.strip():
        raise ToolError("Vendor name is required.")
    candidates = []
    for path in INVOICE_DIR.glob("*.json"):
        data = _load_json(path)
        if vendor.casefold() in str(data.get("vendor", "")).casefold():
            candidates.append((str(data.get("invoice_date", "")), data))
    if not candidates:
        raise ToolError(f"No invoice found for vendor '{vendor}'.")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]

def read_invoice(invoice_id: str) -> dict[str, Any]:
    for path in INVOICE_DIR.glob("*.json"):
        data = _load_json(path)
        if data.get("invoice_id") == invoice_id:
            required = ("invoice_id", "vendor", "amount", "currency", "due_date", "invoice_date")
            missing = [field for field in required if field not in data]
            if missing:
                raise ToolError(f"Invoice {invoice_id} is missing fields: {', '.join(missing)}")
            try:
                amount = float(data["amount"])
            except (TypeError, ValueError):
                raise ToolError(f"Invoice {invoice_id} has an invalid amount.")
            if amount <= 0:
                raise ToolError(f"Invoice {invoice_id} amount must be greater than zero.")
            return {**data, "amount": amount}
    raise ToolError(f"Invoice ID '{invoice_id}' not found.")

def _records() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RECORDS_PATH.exists():
        RECORDS_PATH.write_text("[]", encoding="utf-8")
    value = _load_json(RECORDS_PATH)
    if not isinstance(value, list):
        raise ToolError("invoice_records.json must contain a JSON list.")
    return value

def lookup_record(invoice_id: str) -> dict[str, Any] | None:
    for record in _records():
        if record.get("invoice_id") == invoice_id:
            return record
    return None

def write_record(invoice: dict[str, Any], simulate_failure: bool = False) -> dict[str, Any]:
    if simulate_failure:
        raise ToolError("Simulated temporary write failure.")
    existing = lookup_record(invoice["invoice_id"])
    if existing:
        raise ToolError(f"Duplicate write blocked for invoice {invoice['invoice_id']}.")
    records = _records()
    saved = {**invoice, "processed_at": datetime.now(timezone.utc).isoformat(), "status": "processed"}
    records.append(saved)
    temp_path = RECORDS_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    os.replace(temp_path, RECORDS_PATH)
    return saved

def verify_record(invoice_id: str, expected: dict[str, Any]) -> dict[str, Any]:
    actual = lookup_record(invoice_id)
    if actual is None:
        raise ToolError(f"Record {invoice_id} was not found after writing.")
    for key in ("invoice_id", "vendor", "amount", "currency", "due_date"):
        if str(actual.get(key)) != str(expected.get(key)):
            raise ToolError(f"Verification mismatch for '{key}': expected {expected.get(key)!r}, got {actual.get(key)!r}.")
    return actual

def append_audit(entry: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
