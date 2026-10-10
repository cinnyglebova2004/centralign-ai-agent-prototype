import json
import os
import streamlit as st
from agent import AutonomousInvoiceAgent
from tools import AUDIT_PATH, RECORDS_PATH, INVOICE_DIR

st.set_page_config(page_title="CentrAlign AI | Invoice Agent", page_icon="🤖", layout="wide")
st.title("🤖 CentrAlign AI — Autonomous Invoice Agent")
st.caption("Upgraded proof of concept · plan → use tools → observe → recover → verify")
st.warning("Demo environment only: company records are simulated JSON files. This app does not make payments or connect to a real accounting system.")

with st.sidebar:
    st.header("Run controls")
    st.write("Planner:", "LLM (if OPENAI_API_KEY is set)" if os.getenv("OPENAI_API_KEY") else "Rule-based fallback")
    st.write("Model:", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    simulate_failure = st.checkbox("Simulate one temporary write failure")
    st.caption("The agent first previews a new invoice. You approve that specific invoice in a separate step.")
    st.divider()
    st.subheader("Demo data")
    st.write(f"Invoice files: {len(list(INVOICE_DIR.glob('*.json')))}")
    st.write(f"Company record file: `{RECORDS_PATH.relative_to(RECORDS_PATH.parent.parent.parent)}`")
    if st.button("Show audit log"):
        if AUDIT_PATH.exists():
            st.session_state["audit_display"] = AUDIT_PATH.read_text(encoding="utf-8")
        else:
            st.session_state["audit_display"] = "(No audit events yet.)"

request = st.text_area(
    "What should the agent do?",
    value="Process the latest invoice for ACME Supplies",
    height=90,
    help="Try: 'Process the latest invoice for Northstar Office'.",
)

def _store_result(result):
    st.session_state["last_result"] = {
        "status": result.status, "summary": result.summary, "plan": result.plan,
        "events": result.events, "result": result.result, "approval_required": result.approval_required
    }

if st.button("Run agent", type="primary"):
    # First pass always runs without write approval. Approval is a separate,
    # explicit action tied to the invoice returned by this preview.
    agent = AutonomousInvoiceAgent(max_retries=2)
    result = agent.run(request, approved=False, simulate_failure=simulate_failure)
    _store_result(result)
    if result.status == "approval_required" and result.result:
        st.session_state["pending_approval"] = {
            "request": request,
            "invoice_id": result.result.get("invoice_id"),
            "simulate_failure": simulate_failure,
        }
    else:
        st.session_state.pop("pending_approval", None)

pending = st.session_state.get("pending_approval")
if pending:
    current_result = st.session_state.get("last_result", {})
    if current_result.get("status") == "approval_required":
        preview = current_result.get("result") or {}
        st.warning("Approval required. Review this exact invoice before authorizing a write.")
        st.json({key: preview.get(key) for key in ("invoice_id", "vendor", "amount", "currency", "due_date")})
        confirm = st.checkbox(
            f"I approve writing invoice {pending['invoice_id']} for {preview.get('currency', '')} {preview.get('amount', '')}",
            key=f"approval_{pending['invoice_id']}",
        )
        if st.button("Approve and execute", disabled=not confirm, type="primary"):
            agent = AutonomousInvoiceAgent(max_retries=2)
            result = agent.run(
                pending["request"], approved=True,
                simulate_failure=pending["simulate_failure"],
            )
            _store_result(result)
            st.session_state.pop("pending_approval", None)
            st.rerun()

result = st.session_state.get("last_result")
if result:
    st.subheader("Outcome")
    statuses = {
        "completed": "✅ Completed and verified",
        "approval_required": "🟡 Waiting for approval",
        "duplicate": "🛡️ Duplicate prevented",
        "needs_input": "❓ More information required",
        "failed": "❌ Failed safely",
        "verification_failed": "⚠️ Verification failed",
    }
    st.markdown(f"### {statuses.get(result['status'], result['status'])}")
    st.write(result["summary"])
    left, right = st.columns(2)
    with left:
        st.subheader("Plan")
        for i, step in enumerate(result["plan"], 1):
            st.write(f"{i}. {step}")
    with right:
        st.subheader("Result / evidence")
        if result["result"] is not None:
            st.json(result["result"])
        else:
            st.info("No record was written in this run.")
    st.subheader("Execution trace")
    for event in result["events"]:
        with st.expander(f"{event['step']:02d} · {event['kind'].upper()} · {event['message']}", expanded=event["kind"] in {"error", "retry", "verification", "approval"}):
            if event.get("details"):
                st.json(event["details"])
    if AUDIT_PATH.exists():
        st.caption(f"Audit log: {AUDIT_PATH}")
if "audit_display" in st.session_state:
    st.subheader("Audit log")
    st.code(st.session_state["audit_display"], language="json")

with st.expander("About this prototype"):
    st.markdown("""
- **Planner:** optional OpenAI-compatible planning call; deterministic fallback if no key is configured.
- **Tools:** find invoice, validate invoice, look up duplicates, write record, verify record.
- **Safety:** human approval before writing; duplicate writes blocked by the tool; bounded retries.
- **Verification:** reads the saved record back and compares key fields.
- **Limitations:** invoice-specific; local JSON simulation; no OCR, live accounting API, payment execution, or general-purpose task support.
""")
