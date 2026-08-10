"""
Core Banking MCP Server

Tools:
    get_customer_account_summary(enterprise_customer_id)
    get_transaction_summary(enterprise_customer_id, days=90)
    get_customer_flags(enterprise_customer_id)

Deliberately NOT exposed: update_account_balance, update_account,
delete_transaction, execute_sql. See demo scenario 2 in the project
doc -- a request to modify a balance must be rejected by the
orchestrator's tool-discovery step before it ever reaches this file.

=========================== SAP SWAP -- ACTIVE ===========================
This file has TWO modes, controlled by the CORE_BANKING_SAP_URL
environment variable:

  - CORE_BANKING_SAP_URL is unset  -> reads from data/core_banking.db
                                       (fake SQLite, original POC data source)
  - CORE_BANKING_SAP_URL is set    -> calls the real SAP BTP Cloud Foundry
                                       service (see sap_service/main.py)
                                       over HTTP instead

Either way, this file returns the identical standard envelope, so the
orchestrator, policy engine, and frontend never know or care which
mode is active. To go live with SAP:

    export CORE_BANKING_SAP_URL=https://core-banking-service.<your-cf-domain>.hana.ondemand.com

Restart the FastAPI app after setting this -- the mode is read once
at import time.
============================================================================
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

import requests

from mcp_servers.common.envelope import ok, fail
from mcp_servers.common.identity import ECID_TO_CUST

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "core_banking.db")
SOURCE_SQLITE = "CORE_BANKING"
SOURCE_SAP = "CORE_BANKING_SAP"

SAP_BASE_URL = os.environ.get("CORE_BANKING_SAP_URL", "").rstrip("/")
SAP_TIMEOUT_SECONDS = float(os.environ.get("CORE_BANKING_SAP_TIMEOUT", "5"))
USING_SAP = bool(SAP_BASE_URL)


def _conn():
    return sqlite3.connect(DB_PATH)


# ---------------------------------------------------------------- SQLite path

def _sqlite_account_summary(enterprise_customer_id: str) -> dict:
    cust_id = ECID_TO_CUST.get(enterprise_customer_id)
    if not cust_id:
        return fail("CUSTOMER_NOT_FOUND", "No core banking record for this customer.", SOURCE_SQLITE)

    con = _conn()
    cur = con.cursor()
    cur.execute(
        "SELECT account_id, account_type, current_balance, available_balance, status "
        "FROM accounts WHERE customer_id = ?",
        (cust_id,),
    )
    rows = cur.fetchall()
    con.close()

    if not rows:
        return fail("NO_ACCOUNTS_FOUND", "No accounts on file for this customer.", SOURCE_SQLITE)

    accounts = [
        {"account_id": r[0], "account_type": r[1], "current_balance": r[2], "available_balance": r[3], "status": r[4]}
        for r in rows
    ]
    return ok({"accounts": accounts}, SOURCE_SQLITE)


def _sqlite_transaction_summary(enterprise_customer_id: str, days: int) -> dict:
    cust_id = ECID_TO_CUST.get(enterprise_customer_id)
    if not cust_id:
        return fail("CUSTOMER_NOT_FOUND", "No core banking record for this customer.", SOURCE_SQLITE)

    con = _conn()
    cur = con.cursor()
    cur.execute("SELECT account_id FROM accounts WHERE customer_id = ?", (cust_id,))
    account_ids = [r[0] for r in cur.fetchall()]
    if not account_ids:
        con.close()
        return fail("NO_ACCOUNTS_FOUND", "No accounts on file for this customer.", SOURCE_SQLITE)

    cutoff = (datetime(2026, 8, 1) - timedelta(days=days)).strftime("%Y-%m-%d")
    q_marks = ",".join("?" for _ in account_ids)
    cur.execute(
        f"SELECT balance_after FROM transactions WHERE account_id IN ({q_marks}) AND transaction_date >= ?",
        (*account_ids, cutoff),
    )
    balances = [r[0] for r in cur.fetchall()]
    con.close()

    avg_balance = round(sum(balances) / len(balances), 2) if balances else 0.0
    return ok({"average_balance": avg_balance, "period_days": days, "sample_size": len(balances)}, SOURCE_SQLITE)


def _sqlite_flags(enterprise_customer_id: str) -> dict:
    cust_id = ECID_TO_CUST.get(enterprise_customer_id)
    if not cust_id:
        return fail("CUSTOMER_NOT_FOUND", "No core banking record for this customer.", SOURCE_SQLITE)

    con = _conn()
    cur = con.cursor()
    cur.execute(
        "SELECT flag_type, severity, status, description FROM account_flags "
        "WHERE customer_id = ? AND status = 'ACTIVE'",
        (cust_id,),
    )
    rows = cur.fetchall()
    con.close()

    flags = [{"flag_type": r[0], "severity": r[1], "status": r[2], "description": r[3]} for r in rows]
    return ok({"active_flags": flags, "active_flag_count": len(flags)}, SOURCE_SQLITE)


# ------------------------------------------------------------------- SAP path

def _sap_get(path: str) -> tuple[bool, dict | None, str | None]:
    """Returns (success, json_body_or_None, error_message_or_None)."""
    try:
        resp = requests.get(f"{SAP_BASE_URL}{path}", timeout=SAP_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        return False, None, f"SAP BTP service unreachable: {exc}"

    if resp.status_code == 404:
        return False, None, "CUSTOMER_NOT_FOUND"
    if resp.status_code != 200:
        return False, None, f"SAP BTP service returned HTTP {resp.status_code}"

    return True, resp.json(), None


def _sap_account_summary(enterprise_customer_id: str) -> dict:
    success, data, error = _sap_get(f"/accounts/{enterprise_customer_id}")
    if not success:
        code = "CUSTOMER_NOT_FOUND" if error == "CUSTOMER_NOT_FOUND" else "SAP_SERVICE_ERROR"
        return fail(code, error, SOURCE_SAP)
    return ok(data, SOURCE_SAP)


def _sap_transaction_summary(enterprise_customer_id: str, days: int) -> dict:
    success, data, error = _sap_get(f"/transactions/{enterprise_customer_id}?days={days}")
    if not success:
        code = "CUSTOMER_NOT_FOUND" if error == "CUSTOMER_NOT_FOUND" else "SAP_SERVICE_ERROR"
        return fail(code, error, SOURCE_SAP)
    return ok(data, SOURCE_SAP)


def _sap_flags(enterprise_customer_id: str) -> dict:
    success, data, error = _sap_get(f"/flags/{enterprise_customer_id}")
    if not success:
        code = "CUSTOMER_NOT_FOUND" if error == "CUSTOMER_NOT_FOUND" else "SAP_SERVICE_ERROR"
        return fail(code, error, SOURCE_SAP)
    return ok(data, SOURCE_SAP)


# --------------------------------------------------------------- public tools

def get_customer_account_summary(enterprise_customer_id: str) -> dict:
    if USING_SAP:
        return _sap_account_summary(enterprise_customer_id)
    return _sqlite_account_summary(enterprise_customer_id)


def get_transaction_summary(enterprise_customer_id: str, days: int = 90) -> dict:
    if USING_SAP:
        return _sap_transaction_summary(enterprise_customer_id, days)
    return _sqlite_transaction_summary(enterprise_customer_id, days)


def get_customer_flags(enterprise_customer_id: str) -> dict:
    if USING_SAP:
        return _sap_flags(enterprise_customer_id)
    return _sqlite_flags(enterprise_customer_id)


# NOTE: no update_account_balance / update_account / delete_transaction /
# execute_sql tool is registered here. This is intentional -- see
# demo scenario 2 (controlled capability rejection).
TOOLS = {
    "get_customer_account_summary": get_customer_account_summary,
    "get_transaction_summary": get_transaction_summary,
    "get_customer_flags": get_customer_flags,
}
