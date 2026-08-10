"""
CRM MCP Server

Tools:
    find_customer(name) -> ECID
    get_customer_value(enterprise_customer_id) -> tier, lifetime value, etc.

Backed by a real Postgres database (Neon), not local fake SQLite --
this is the "different kind of DB" domain. Connection comes from
DATABASE_URL in .env. Deliberately exposes nothing else -- no write
tools, no arbitrary query tool.
"""
from __future__ import annotations

import os

import psycopg2
from dotenv import load_dotenv

from mcp_servers.common.envelope import ok, fail
from mcp_servers.common.identity import find_ecid_by_name, ECID_TO_CRM

load_dotenv()

SOURCE = "CRM_POSTGRES"


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def find_customer(name: str) -> dict:
    ecid = find_ecid_by_name(name)
    if not ecid:
        return fail("CUSTOMER_NOT_FOUND", f"No customer matching '{name}' was found.", SOURCE)
    return ok({"enterprise_customer_id": ecid, "matched_name": name}, SOURCE)


def get_customer_value(enterprise_customer_id: str) -> dict:
    crm_id = ECID_TO_CRM.get(enterprise_customer_id)
    if not crm_id:
        return fail("CUSTOMER_NOT_FOUND", "No CRM record for this customer.", SOURCE)

    try:
        con = _conn()
        cur = con.cursor()
        cur.execute(
            "SELECT p.customer_segment, v.lifetime_value, v.annual_revenue, v.products_held, v.customer_score "
            "FROM customer_profile p JOIN customer_value v ON p.crm_customer_id = v.crm_customer_id "
            "WHERE p.crm_customer_id = %s",
            (crm_id,),
        )
        row = cur.fetchone()
        con.close()
    except (psycopg2.OperationalError, KeyError) as exc:
        return fail("SERVICE_UNAVAILABLE", f"CRM database unreachable: {exc}", SOURCE)

    if not row:
        return fail("CRM_RECORD_MISSING", "CRM profile/value record missing.", SOURCE)

    tier, ltv, revenue, products, score = row
    return ok(
        {
            "customer_tier": tier,
            "lifetime_value": float(ltv),
            "annual_revenue": float(revenue),
            "products_held": products,
            "customer_score": score,
        },
        SOURCE,
    )


TOOLS = {
    "find_customer": find_customer,
    "get_customer_value": get_customer_value,
}
