"""
AP (Accounts Payable) MCP Server

Tools:
    find_vendor(name) -> vendor ID
    get_vendor_reconciliation(lifnr) -> PO value, invoiced amount, open items

Backed by the sap_ap_service deployed on SAP BTP (real vendors, POs,
goods receipts, invoices -- see sap_ap_service/main.py). Connection
comes from AP_SAP_URL in .env.

Deliberately exposes nothing else -- no vendor create/edit, no
payment-execution tool.
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

from mcp_servers.common.envelope import ok, fail

load_dotenv()

SOURCE = "AP_SAP"
AP_BASE_URL = os.environ.get("AP_SAP_URL", "").rstrip("/")
AP_TIMEOUT_SECONDS = float(os.environ.get("AP_SAP_TIMEOUT", "8"))


def _get(path: str):
    if not AP_BASE_URL:
        return None, "AP_SAP_URL is not configured."
    try:
        resp = requests.get(f"{AP_BASE_URL}{path}", timeout=AP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return None, f"AP service unreachable: {exc}"
    if resp.status_code == 404:
        return None, "NOT_FOUND"
    if resp.status_code != 200:
        return None, f"AP service returned HTTP {resp.status_code}"
    return resp.json(), None


def find_vendor(name: str) -> dict:
    data, error = _get(f"/vendors/search?name={name}")
    if error:
        code = "SERVICE_UNAVAILABLE" if error != "NOT_FOUND" else "VENDOR_NOT_FOUND"
        return fail(code, error, SOURCE)
    vendors = data.get("vendors", [])
    if not vendors:
        return fail("VENDOR_NOT_FOUND", f"No vendor matching '{name}' was found.", SOURCE)
    v = vendors[0]
    return ok({"vendor_id": v["LIFNR"], "matched_name": v["NAME1"], "country": v["LAND1"]}, SOURCE)


def get_vendor_reconciliation(vendor_id: str) -> dict:
    data, error = _get(f"/vendors/{vendor_id}/summary")
    if error:
        code = "SERVICE_UNAVAILABLE" if error != "NOT_FOUND" else "VENDOR_NOT_FOUND"
        return fail(code, error, SOURCE)
    return ok(
        {
            "vendor_name": data["vendor"]["NAME1"],
            "purchase_order_count": data["purchase_order_count"],
            "total_po_value": data["total_po_value"],
            "total_invoiced": data["total_invoiced"],
            "total_invoice_items": data["total_invoice_items"],
            "open_items": data["open_items"],
        },
        SOURCE,
    )


TOOLS = {
    "find_vendor": find_vendor,
    "get_vendor_reconciliation": get_vendor_reconciliation,
}
