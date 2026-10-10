import json
from pathlib import Path
import pytest
import tools
from agent import AutonomousInvoiceAgent

@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    data_dir = tmp_path / "company_system"
    invoice_dir = tmp_path / "invoices"
    log_dir = tmp_path / "logs"
    data_dir.mkdir()
    invoice_dir.mkdir()
    log_dir.mkdir()
    invoice = {
        "invoice_id": "TEST-001", "vendor": "ACME Supplies",
        "amount": 100.0, "currency": "INR",
        "due_date": "2026-11-30", "invoice_date": "2026-10-01"
    }
    (invoice_dir / "test.json").write_text(json.dumps(invoice), encoding="utf-8")
    (data_dir / "invoice_records.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(tools, "DATA_DIR", data_dir)
    monkeypatch.setattr(tools, "INVOICE_DIR", invoice_dir)
    monkeypatch.setattr(tools, "LOG_DIR", log_dir)
    monkeypatch.setattr(tools, "RECORDS_PATH", data_dir / "invoice_records.json")
    monkeypatch.setattr(tools, "AUDIT_PATH", log_dir / "audit.jsonl")
    return invoice

def test_requires_approval_before_write(isolated_data):
    result = AutonomousInvoiceAgent().run("Process the latest invoice for ACME Supplies", approved=False)
    assert result.status == "approval_required"
    assert tools.lookup_record("TEST-001") is None

def test_success_with_retry_and_verification(isolated_data):
    result = AutonomousInvoiceAgent().run(
        "Process the latest invoice for ACME Supplies", approved=True, simulate_failure=True
    )
    assert result.status == "completed"
    assert any(event["kind"] == "retry" for event in result.events)
    assert any(event["kind"] == "verification" for event in result.events)
    assert tools.lookup_record("TEST-001") is not None

def test_duplicate_is_not_written(isolated_data):
    tools.write_record(isolated_data)
    result = AutonomousInvoiceAgent().run("Process the latest invoice for ACME Supplies", approved=True)
    assert result.status == "duplicate"
    assert len(json.loads(tools.RECORDS_PATH.read_text(encoding="utf-8"))) == 1

def test_unknown_vendor_fails_safely(isolated_data):
    result = AutonomousInvoiceAgent().run("Process the latest invoice for Unknown Company", approved=True)
    assert result.status == "failed"
