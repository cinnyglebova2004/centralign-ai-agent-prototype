
import json, os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(ROOT, "data", "invoices")
RECORDS_FILE = os.path.join(ROOT, "data", "company_system", "invoice_records.json")
LOG_DIR = os.path.join(ROOT, "logs")

def load_invoices():
    rows = []
    for name in sorted(os.listdir(INVOICE_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(INVOICE_DIR, name), encoding="utf-8") as f:
                item = json.load(f)
            item["file_name"] = name
            rows.append(item)
    return rows

def find_latest_invoice(vendor):
    matches = [x for x in load_invoices() if x.get("vendor", "").casefold() == vendor.casefold()]
    if not matches:
        return None
    matches.sort(key=lambda x: x.get("invoice_date", ""), reverse=True)
    item = matches[0]
    return {"file_name": item["file_name"], "path": os.path.join(INVOICE_DIR, item["file_name"])}

def read_invoice(invoice_ref):
    with open(invoice_ref["path"], encoding="utf-8") as f:
        return json.load(f)

def _read_records():
    os.makedirs(os.path.dirname(RECORDS_FILE), exist_ok=True)
    if not os.path.exists(RECORDS_FILE):
        return []
    with open(RECORDS_FILE, encoding="utf-8") as f:
        return json.load(f)

def load_records():
    return _read_records()

def lookup_record(invoice_id):
    return next((r for r in _read_records() if r.get("invoice_id") == invoice_id), None)

def write_record(payload):
    records = _read_records()
    if any(r.get("invoice_id") == payload["invoice_id"] for r in records):
        raise ValueError("Duplicate invoice ID blocked by internal system")
    records.append(payload)
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

def verify_record(invoice_id, expected):
    actual = lookup_record(invoice_id)
    if not actual:
        return False
    keys = ["invoice_id", "vendor", "amount", "currency", "due_date"]
    return all(str(actual.get(k)) == str(expected.get(k)) for k in keys)

def append_audit(event):
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, "audit.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), **event}) + "\n")
    return path
