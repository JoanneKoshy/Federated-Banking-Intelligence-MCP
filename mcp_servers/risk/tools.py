"""
Risk MCP Server

Tools:
    get_credit_risk(enterprise_customer_id)
    get_mortgage_status(enterprise_customer_id)

Backed by data/credit_risk.csv and data/loans.csv (fake CSVs).

This server can be shut down independently to run the "Risk MCP
unavailable" fail-closed demo (see api/main.py: /api/admin/toggle-risk).
"""
from __future__ import annotations

import csv
import os

from mcp_servers.common.envelope import ok, fail
from mcp_servers.common.identity import ECID_TO_RISK

HERE = os.path.dirname(__file__)
RISK_CSV = os.path.join(HERE, "..", "..", "data", "credit_risk.csv")
LOANS_CSV = os.path.join(HERE, "..", "..", "data", "loans.csv")
SOURCE = "RISK"

# In-memory toggle used purely for the "Risk MCP unavailable" demo scenario.
_SERVER_AVAILABLE = {"value": True}


def set_availability(available: bool) -> None:
    _SERVER_AVAILABLE["value"] = available


def _unavailable_check():
    if not _SERVER_AVAILABLE["value"]:
        return fail("SERVICE_UNAVAILABLE", "Risk MCP server is currently unavailable.", SOURCE)
    return None


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def get_credit_risk(enterprise_customer_id: str) -> dict:
    unavailable = _unavailable_check()
    if unavailable:
        return unavailable

    rows = _read_csv(RISK_CSV)
    for row in rows:
        if row["enterprise_customer_id"] == enterprise_customer_id:
            return ok(
                {
                    "risk_rating": row["risk_rating"],
                    "credit_score": int(row["credit_score"]),
                    "total_exposure": float(row["total_exposure"]),
                    "delinquency_days": int(row["delinquency_days"]),
                    "last_assessment": row["last_assessment"],
                },
                SOURCE,
            )
    return fail("CUSTOMER_NOT_FOUND", "No risk record for this customer.", SOURCE)


def get_mortgage_status(enterprise_customer_id: str) -> dict:
    unavailable = _unavailable_check()
    if unavailable:
        return unavailable

    risk_id = ECID_TO_RISK.get(enterprise_customer_id)
    if not risk_id:
        return fail("CUSTOMER_NOT_FOUND", "No risk record for this customer.", SOURCE)

    rows = _read_csv(LOANS_CSV)
    mortgages = [r for r in rows if r["risk_customer_id"] == risk_id and r["loan_type"] == "MORTGAGE"]
    if not mortgages:
        return ok({"has_mortgage": False, "payment_status": None}, SOURCE)

    loan = mortgages[0]
    return ok(
        {
            "has_mortgage": True,
            "payment_status": loan["payment_status"],
            "outstanding_amount": float(loan["outstanding_amount"]),
            "status": loan["status"],
        },
        SOURCE,
    )


TOOLS = {
    "get_credit_risk": get_credit_risk,
    "get_mortgage_status": get_mortgage_status,
}
