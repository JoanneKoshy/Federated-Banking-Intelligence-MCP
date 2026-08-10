"""
Bounded orchestration "graph" -- now a real MCP CLIENT.

This intentionally is NOT an autonomous agent loop. It is a fixed,
predefined sequence of steps -- classify intent, resolve customer,
call MCP tools (over the real MCP protocol, via agent/mcp_client.py)
in a fixed order, validate evidence, call policy, compose a grounded
response. No free-form planning, no arbitrary retries beyond one
controlled retry per tool.

Every _call() below talks to a real, separate MCP server process
(see mcp_servers/*/server.py) over stdio, using the official `mcp`
Python SDK -- not a direct Python function call.
"""
from __future__ import annotations

import time

from agent.intent import extract
from agent.state import BankingAgentState
from agent import llm
from agent import mcp_client

REQUIRED_EVIDENCE_KEYS = ["crm", "account", "flags", "risk", "mortgage"]


async def _call(state: BankingAgentState, mcp_server: str, tool_name: str, **kwargs) -> dict:
    """Call a tool on a real MCP server, record it in the execution trace, one controlled retry on failure."""
    start = time.perf_counter()
    result = await mcp_client.call_tool(mcp_server, tool_name, **kwargs)
    if not result["success"]:
        result = await mcp_client.call_tool(mcp_server, tool_name, **kwargs)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    step = {
        "sequence": len(state["trace"]) + 1,
        "mcp_server": result.get("source") or mcp_server,
        "tool": tool_name,
        "input": kwargs,
        "output_summary": result["data"] if result["success"] else None,
        "status": "SUCCESS" if result["success"] else "FAILURE",
        "error": result["error"]["message"] if result["error"] else None,
        "duration_ms": duration_ms,
    }
    state["trace"].append(step)
    return result


async def run_fee_waiver_assessment(state: BankingAgentState) -> BankingAgentState:
    ecid = state["enterprise_customer_id"]
    evidence = {}

    crm_val = await _call(state, "crm", "get_customer_value", enterprise_customer_id=ecid)
    if crm_val["success"]:
        evidence["crm"] = crm_val["data"]

    acct = await _call(state, "core_banking", "get_customer_account_summary", enterprise_customer_id=ecid)
    txn = await _call(state, "core_banking", "get_transaction_summary", enterprise_customer_id=ecid, days=90)
    flags = await _call(state, "core_banking", "get_customer_flags", enterprise_customer_id=ecid)
    if acct["success"]:
        evidence["account"] = acct["data"]
    if txn["success"]:
        evidence["average_balance"] = txn["data"]["average_balance"]
    if flags["success"]:
        evidence["flags"] = flags["data"]

    risk = await _call(state, "risk", "get_credit_risk", enterprise_customer_id=ecid)
    mortgage = await _call(state, "risk", "get_mortgage_status", enterprise_customer_id=ecid)
    if risk["success"]:
        evidence["risk"] = risk["data"]
    if mortgage["success"]:
        evidence["mortgage"] = mortgage["data"]

    state["evidence"] = evidence

    missing = [k for k in ["crm", "account", "flags", "risk", "mortgage"] if k not in evidence]
    if missing:
        state["status"] = "NO_DECISION"
        state["final_message"] = (
            "DECISION NOT AVAILABLE. Required evidence is missing from: "
            + ", ".join(missing)
            + ". Eligibility cannot be determined."
        )
        return state

    policy = await _call(
        state,
        "policy",
        "check_fee_waiver_eligibility",
        customer_tier=evidence["crm"]["customer_tier"],
        lifetime_value=evidence["crm"]["lifetime_value"],
        average_balance=evidence["average_balance"],
        risk_rating=evidence["risk"]["risk_rating"],
        delinquency_days=evidence["risk"]["delinquency_days"],
        active_flags=evidence["flags"]["active_flag_count"],
        mortgage_payment_status=evidence["mortgage"]["payment_status"],
        fee_amount=state["fee_amount"],
    )

    if not policy["success"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = "DECISION NOT AVAILABLE. Policy service could not evaluate this request."
        return state

    state["policy_result"] = policy["data"]
    state["status"] = "OK"
    state["final_message"] = compose_response(state)
    return state


def compose_response(state: BankingAgentState) -> str:
    """
    Response composer contract: use only facts present in the evidence
    object, never override policy_result.decision, never invent facts.

    Tries the LLM first (grounded strictly in the evidence dict, same
    contract); falls back to the deterministic template on any failure.
    """
    ev = state["evidence"]
    pol = state["policy_result"]
    decision = pol["decision"]

    llm_text = llm.compose_response_llm(decision, pol["policy"], ev, pol["reason_codes"])
    if llm_text:
        return llm_text

    reasons = ", ".join(pol["reason_codes"])
    lines = [
        f"Decision: {decision} (policy {pol['policy']})",
        f"Customer tier: {ev['crm']['customer_tier']}",
        f"Lifetime value: Rs {ev['crm']['lifetime_value']:,.0f}",
        f"90-day average balance: Rs {ev['average_balance']:,.0f}",
        f"Risk rating: {ev['risk']['risk_rating']}",
        f"Active flags: {ev['flags']['active_flag_count']}",
        f"Mortgage status: {ev['mortgage'].get('payment_status') or 'N/A'}",
        f"Reason codes: {reasons}",
    ]
    return "\n".join(lines)


async def run_vendor_reconciliation(state: BankingAgentState) -> BankingAgentState:
    vendor_name = state["customer_name"]

    lookup = await _call(state, "ap", "find_vendor", name=vendor_name)
    if not lookup["success"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = (
            "UNABLE TO EVALUATE. No matching vendor was found in the authorized "
            "AP systems. No reconciliation decision has been generated."
        )
        return state

    vendor_id = lookup["data"]["vendor_id"]

    recon = await _call(state, "ap", "get_vendor_reconciliation", vendor_id=vendor_id)
    if not recon["success"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = "DECISION NOT AVAILABLE. Vendor reconciliation data could not be retrieved."
        return state

    state["evidence"] = {"vendor": recon["data"]}

    policy = await _call(
        state,
        "ap_policy",
        "check_vendor_reconciliation",
        open_items=recon["data"]["open_items"],
        total_invoice_items=recon["data"]["total_invoice_items"],
        total_po_value=recon["data"]["total_po_value"],
        total_invoiced=recon["data"]["total_invoiced"],
    )
    if not policy["success"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = "DECISION NOT AVAILABLE. AP policy could not evaluate this vendor."
        return state

    state["policy_result"] = policy["data"]
    state["status"] = "OK"

    v = recon["data"]
    p = policy["data"]

    llm_text = llm.compose_response_llm(p["decision"], p["policy"], {"vendor": v}, p["reason_codes"])
    if llm_text:
        state["final_message"] = llm_text
        return state

    state["final_message"] = "\n".join([
        f"Decision: {p['decision']} (policy {p['policy']})",
        f"Vendor: {v['vendor_name']}",
        f"Purchase orders: {v['purchase_order_count']}",
        f"Total PO value: Rs {v['total_po_value']:,.0f}",
        f"Total invoiced: Rs {v['total_invoiced']:,.0f}",
        f"Open items: {v['open_items']} of {v['total_invoice_items']} ({p['open_item_pct']}%)",
        f"Reason codes: {', '.join(p['reason_codes'])}",
    ])
    return state


async def run(query: str) -> BankingAgentState:
    state: BankingAgentState = {
        "query": query,
        "trace": [],
        "evidence": {},
        "policy_result": None,
        "status": "OK",
        "error": None,
    }

    extracted = extract(query)
    state["intent"] = extracted["intent"]
    state["customer_name"] = extracted.get("customer_name")
    state["fee_amount"] = extracted.get("fee_amount") or 0.0

    if state["intent"] == "UNSUPPORTED_OPERATION":
        state["status"] = "REJECTED"
        state["final_message"] = (
            "REQUEST REJECTED.\n"
            "No authorized MCP capability exists for this operation.\n"
            "The database was never reached."
        )
        return state

    if not state["customer_name"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = "Could not identify a customer or vendor name in the request."
        return state

    if state["intent"] == "VENDOR_RECONCILIATION":
        return await run_vendor_reconciliation(state)

    lookup = await _call(state, "crm", "find_customer", name=state["customer_name"])
    if not lookup["success"]:
        state["status"] = "NO_DECISION"
        state["final_message"] = (
            "UNABLE TO EVALUATE. No matching customer was found in the authorized "
            "customer systems. No eligibility decision has been generated."
        )
        return state

    state["enterprise_customer_id"] = lookup["data"]["enterprise_customer_id"]

    if state["intent"] == "FEE_WAIVER_ASSESSMENT":
        return await run_fee_waiver_assessment(state)

    if state["intent"] == "CUSTOMER_LOOKUP":
        val = await _call(state, "crm", "get_customer_value", enterprise_customer_id=state["enterprise_customer_id"])
        state["evidence"] = {"crm": val["data"]} if val["success"] else {}
        state["final_message"] = (
            f"{state['customer_name']} ({state['enterprise_customer_id']}): "
            f"{val['data']}" if val["success"] else "Customer found but CRM detail unavailable."
        )
        return state

    state["status"] = "NO_DECISION"
    state["final_message"] = "Unsupported request."
    return state
