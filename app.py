
import streamlit as st
from agent import AutonomousInvoiceAgent
from tools import load_invoices, load_records

st.set_page_config(page_title="CentrAlign AI | Task Worker", page_icon="🤖", layout="wide")
st.title("Autonomous AI Task Worker")
st.caption("A small, auditable prototype: natural-language goal → plan → tools → verification.")

with st.sidebar:
    st.subheader("Demo environment")
    st.write("Uses sample invoice files and a simulated internal company system.")
    st.info("No real company credentials or external systems are used.")
    st.write("Supported task: find the latest invoice for a vendor and record it.")
    fail_once = st.checkbox("Simulate one temporary tool failure", value=False)
    require_approval = st.checkbox("Require approval before writing", value=True)
    approve_write = st.checkbox("I approve writing the extracted invoice fields to the simulated system", value=False)

task = st.text_input(
    "What should the AI employee do?",
    value="Find the latest invoice from Acme Supplies, record its amount and due date in the internal system, and verify it."
)
run = st.button("Run task", type="primary")

left, right = st.columns([1, 1])
if run:
    agent = AutonomousInvoiceAgent(fail_once=fail_once, require_approval=require_approval)
    result = agent.run(task, approved=(approve_write or not require_approval))
    st.subheader("Execution result")
    if result["status"] == "completed":
        st.success(result["message"])
    elif result["status"] == "needs_approval":
        st.warning(result["message"])
    else:
        st.error(result["message"])
    with left:
        st.subheader("Plan and execution trace")
        for item in result["trace"]:
            st.markdown(f"- **{item['stage']}**: {item['detail']}")
    with right:
        st.subheader("Evidence")
        if result.get("record"):
            st.json(result["record"])
        st.write("Verification:", result.get("verification", "Not completed"))
        if result.get("audit_file"):
            st.caption(f"Audit log: `{result['audit_file']}`")
else:
    st.subheader("How to try it")
    st.markdown("""
    1. Keep the default task or try `Process the latest invoice from Northstar Office`.
    2. Turn on **Simulate one temporary tool failure** to show retry behavior.
    3. Run the task and inspect the trace, evidence, and verification result.
    """)
    st.subheader("Current sample invoices")
    st.dataframe(load_invoices(), use_container_width=True)
    st.subheader("Current internal records")
    st.dataframe(load_records(), use_container_width=True)
