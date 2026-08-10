"""
AP Policy MCP Server

Tool:
    check_vendor_reconciliation(open_items, total_invoice_items, total_po_value, total_invoiced)

Pure, deterministic rule -- same philosophy as the banking Policy MCP:
no LLM call happens here. The LLM only explains this tool's output
afterward.
"""
from __future__ import annotations

from mcp_servers.common.envelope import ok

SOURCE = "AP_POLICY"
POLICY_ID = "AP-3WAY-01"


def check_vendor_reconciliation(
    open_items: int,
    total_invoice_items: int,
    total_po_value: float,
    total_invoiced: float,
) -> dict:
    open_pct = (open_items / total_invoice_items * 100) if total_invoice_items else 0.0
    over_billed = total_invoiced > total_po_value

    reason_codes = []

    if over_billed:
        decision = "OVER_BILLED"
        reason_codes.append("INVOICED_EXCEEDS_PO_VALUE")
    elif open_pct <= 25:
        decision = "MATCHED"
        reason_codes.append("LOW_OPEN_ITEM_RATE")
    elif open_pct <= 45:
        decision = "REVIEW_RECOMMENDED"
        reason_codes.append("MODERATE_OPEN_ITEM_RATE")
    else:
        decision = "SIGNIFICANT_MISMATCH"
        reason_codes.append("HIGH_OPEN_ITEM_RATE")

    return ok(
        {
            "decision": decision,
            "policy": POLICY_ID,
            "open_item_pct": round(open_pct, 1),
            "reason_codes": reason_codes,
        },
        SOURCE,
    )


TOOLS = {
    "check_vendor_reconciliation": check_vendor_reconciliation,
}
