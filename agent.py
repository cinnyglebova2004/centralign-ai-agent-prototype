

import re
from datetime import datetime

from tools import (
    find_latest_invoice,
    read_invoice,
    lookup_record,
    write_record,
    verify_record,
    append_audit,
)


class AutonomousInvoiceAgent:
    """A bounded invoice agent with retries, approval gates, and verification."""

    def __init__(self, fail_once=False, require_approval=True, max_retries=2):
        self.fail_once = fail_once
        self.require_approval = require_approval
        self.max_retries = max_retries
        self.trace = []

    def log(self, stage, detail):
        self.trace.append({
            "stage": stage,
            "detail": detail,
        })

    def run(self, task, approved=False):
        self.trace = []

        self.log("Understand", f"Received goal: {task}")

        # Step 1: Identify the vendor.
        vendor = self._extract_vendor(task)

        if not vendor:
            msg = (
                "I couldn't identify a vendor. Please name the supplier, "
                "for example: 'Process the latest invoice from Acme Supplies'."
            )
            self.log("Clarify", msg)

            return {
                "status": "needs_input",
                "message": msg,
                "trace": self.trace,
            }

        # Step 2: Plan the task.
        self.log(
            "Plan",
            f"1) Find invoice for {vendor}; "
            "2) read invoice; "
            "3) check duplicates; "
            "4) write record; "
            "5) verify saved record.",
        )

        # Step 3: Find the invoice.
        invoice = find_latest_invoice(vendor)

        if not invoice:
            msg = f"No invoice found for vendor '{vendor}'. No changes were made."
            self.log("Observe", msg)

            return {
                "status": "failed",
                "message": msg,
                "trace": self.trace,
            }

        self.log("Execute", f"Located invoice file: {invoice['file_name']}")

        # Step 4: Read and validate invoice data.
        data = read_invoice(invoice)

        required = [
            "invoice_id",
            "vendor",
            "amount",
            "currency",
            "due_date",
        ]

        missing = [
            key
            for key in required
            if key not in data or data[key] in ("", None)
        ]

        if missing:
            msg = (
                "Invoice is missing required fields: "
                + ", ".join(missing)
                + ". Nothing was written."
            )
            self.log("Validate", msg)

            return {
                "status": "failed",
                "message": msg,
                "trace": self.trace,
            }

        # Validate the amount.
        try:
            amount = float(data["amount"])
            if amount <= 0:
                raise ValueError("Amount must be greater than zero.")
        except (ValueError, TypeError):
            msg = "Invoice amount is invalid. Nothing was written."
            self.log("Validate", msg)

            return {
                "status": "failed",
                "message": msg,
                "trace": self.trace,
            }

        self.log(
            "Observe",
            f"Extracted invoice_id={data['invoice_id']}, "
            f"amount={data['currency']} {amount:.2f}, "
            f"due_date={data['due_date']}.",
        )

        # Step 5: Check for duplicates.
        existing = lookup_record(data["invoice_id"])

        if existing:
            verified = verify_record(data["invoice_id"], existing)

            msg = (
                "This invoice is already recorded. "
                "The existing record was checked; no duplicate was created."
            )

            self.log("Verify", "Duplicate detected; existing record checked.")

            return {
                "status": "completed" if verified else "failed",
                "message": msg,
                "trace": self.trace,
                "record": existing,
                "verification": verified,
            }

        # Step 6: Ask for approval before making a change.
        if self.require_approval and not approved:
            msg = "Approval is required before writing to the internal system."
            self.log("Approval", msg)

            return {
                "status": "needs_approval",
                "message": msg,
                "trace": self.trace,
                "record": data,
            }

        # Step 7: Prepare the record.
        payload = {
            "invoice_id": data["invoice_id"],
            "vendor": data["vendor"],
            "amount": amount,
            "currency": data["currency"],
            "due_date": data["due_date"],
            "source_file": invoice["file_name"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        # Step 8: Write with bounded retries.
        attempts = 0
        write_succeeded = False

        while attempts <= self.max_retries:
            attempts += 1

            try:
                if self.fail_once:
                    self.fail_once = False
                    raise RuntimeError(
                        "Simulated temporary write failure"
                    )

                write_record(payload)
                write_succeeded = True

                self.log(
                    "Execute",
                    f"Write succeeded on attempt {attempts}.",
                )
                break

            except Exception as exc:
                self.log(
                    "Recover",
                    f"Attempt {attempts} failed: {exc}",
                )

                if attempts > self.max_retries:
                    msg = (
                        f"Write failed after {attempts} attempts. "
                        "The agent stopped without claiming success."
                    )

                    append_audit({
                        "task": task,
                        "status": "failed",
                        "trace": self.trace,
                        "invoice_id": data["invoice_id"],
                    })

                    return {
                        "status": "failed",
                        "message": msg,
                        "trace": self.trace,
                    }

        if not write_succeeded:
            return {
                "status": "failed",
                "message": "The invoice could not be written.",
                "trace": self.trace,
            }

        # Step 9: Read the saved record and verify it.
        saved_record = lookup_record(data["invoice_id"])

        verified = (
            saved_record is not None
            and verify_record(data["invoice_id"], payload)
        )

        self.log(
            "Verify",
            "Read-after-write verification: "
            + ("passed." if verified else "failed."),
        )

        status = "completed" if verified else "failed"

        if verified:
            msg = "Invoice recorded and verified."
        else:
            msg = (
                "A record may have been written, but verification failed. "
                "Please inspect the internal system."
            )

        # Step 10: Record the audit trail.
        audit_file = append_audit({
            "task": task,
            "status": status,
            "trace": self.trace,
            "invoice_id": data["invoice_id"],
        })

        return {
            "status": status,
            "message": msg,
            "trace": self.trace,
            "record": saved_record,
            "verification": verified,
            "audit_file": audit_file,
        }

    def _extract_vendor(self, task):
        patterns = [
            r"invoice\s+from\s+(.+?)(?:,|\.|;|$)",
            r"vendor\s+(.+?)(?:,|\.|;|$)",
            r"from\s+(.+?)(?:,|\.|;|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, task, flags=re.IGNORECASE)

            if match:
                return match.group(1).strip().strip("'\"")

        return None
