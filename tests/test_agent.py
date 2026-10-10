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

def test_missing_vendor_requests_clarification(isolated_data):
    result = AutonomousInvoiceAgent().run("Process the latest invoice", approved=True)
    assert result.status == "needs_input"
    assert tools.lookup_record("TEST-001") is None


def test_invalid_amount_is_rejected(isolated_data, tmp_path):
    invoice_path = tools.INVOICE_DIR / "test.json"
    bad = dict(isolated_data, amount=-10)
    invoice_path.write_text(json.dumps(bad), encoding="utf-8")
    result = AutonomousInvoiceAgent().run("Process the latest invoice for ACME Supplies", approved=True)
    assert result.status == "failed"
    assert tools.lookup_record("TEST-001") is None


def test_retry_exhaustion_fails_without_record(isolated_data):
    result = AutonomousInvoiceAgent(max_retries=1).run(
        "Process the latest invoice for ACME Supplies", approved=True, simulate_failure=True
    )
    assert result.status == "failed"
    assert "after 1 attempt" in result.summary
    assert tools.lookup_record("TEST-001") is None


def test_verification_failure_is_reported(isolated_data, monkeypatch):
    def fail_verification(invoice_id, expected):
        raise tools.ToolError("forced verification mismatch")
    monkeypatch.setattr(__import__("agent"), "verify_record", fail_verification)
    result = AutonomousInvoiceAgent().run(
        "Process the latest invoice for ACME Supplies", approved=True
    )
    assert result.status == "verification_failed"
    # The app correctly reports uncertainty: the write exists, but wasn't verified.
    assert tools.lookup_record("TEST-001") is not None


def test_audit_log_records_success(isolated_data):
    result = AutonomousInvoiceAgent().run(
        "Process the latest invoice for ACME Supplies", approved=True
    )
    assert result.status == "completed"
    lines = tools.AUDIT_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    audit = json.loads(lines[0])
    assert audit["status"] == "completed"
    assert audit["invoice_id"] == "TEST-001"


def test_latest_invoice_is_selected(isolated_data):
    newer = dict(isolated_data, invoice_id="TEST-002", invoice_date="2026-10-09")
    (tools.INVOICE_DIR / "newer.json").write_text(json.dumps(newer), encoding="utf-8")
    assert tools.find_latest_invoice("ACME Supplies")["invoice_id"] == "TEST-002"


def test_ambiguous_partial_vendor_match_is_rejected(isolated_data):
    second = dict(isolated_data, invoice_id="TEST-002", vendor="ACME Supplies International")
    (tools.INVOICE_DIR / "second.json").write_text(json.dumps(second), encoding="utf-8")
    with pytest.raises(tools.ToolError, match="ambiguous"):
        tools.find_latest_invoice("ACME")


def test_vendor_match_ignores_punctuation_and_case(isolated_data):
    found = tools.find_latest_invoice(" acme---SUPPLIES ")
    assert found["invoice_id"] == "TEST-001"


def test_corrupt_records_file_fails_safely(isolated_data):
    tools.RECORDS_PATH.write_text("{not-json", encoding="utf-8")
    result = AutonomousInvoiceAgent().run(
        "Process the latest invoice for ACME Supplies", approved=True
    )
    assert result.status == "failed"
    assert any("Invalid JSON" in event["message"] for event in result.events)
