"""
Aggregates portfolio-wide stats across all ~100 synthetic customers, by
querying the real data sources directly (Postgres CRM, CSV Risk, local
SQLite Core Banking flags -- SQLite is used here rather than the SAP
service because the SAP demo service only has the 4 pinned customers'
data hardcoded; the local core_banking.db has flags for all 100).

This is a dashboard/analytics feature, separate from the per-customer
MCP tool-call path used by the chat demo.
"""
from __future__ import annotations

import csv
import os
import sqlite3

import psycopg2
from dotenv import load_dotenv

from mcp_servers.common.identity import ECID_TO_CUST, ECID_TO_CRM

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
RISK_CSV = os.path.join(HERE, "..", "data", "credit_risk.csv")
CORE_BANKING_DB = os.path.join(HERE, "..", "data", "core_banking.db")


def compute_portfolio_stats() -> dict:
    ecids = list(ECID_TO_CUST.keys())
    total = len(ecids)

    crm_by_ecid = {}
    try:
        con = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = con.cursor()
        cur.execute("SELECT enterprise_customer_id, customer_segment FROM customer_profile")
        tier_rows = cur.fetchall()
        cur.execute("""
            SELECT p.enterprise_customer_id, v.lifetime_value
            FROM customer_profile p JOIN customer_value v ON p.crm_customer_id = v.crm_customer_id
        """)
        ltv_rows = cur.fetchall()
        con.close()

        tier_map = dict(tier_rows)
        ltv_map = {ecid: float(ltv) for ecid, ltv in ltv_rows}
        for ecid in ecids:
            crm_by_ecid[ecid] = {"tier": tier_map.get(ecid), "lifetime_value": ltv_map.get(ecid, 0)}
    except Exception:
        crm_by_ecid = {ecid: {"tier": None, "lifetime_value": 0} for ecid in ecids}

    risk_by_ecid = {}
    with open(RISK_CSV, newline="") as f:
        for row in csv.DictReader(f):
            risk_by_ecid[row["enterprise_customer_id"]] = {
                "risk_rating": row["risk_rating"],
                "delinquency_days": int(row["delinquency_days"]),
            }

    flags_by_cust = {}
    con = sqlite3.connect(CORE_BANKING_DB)
    cur = con.cursor()
    cur.execute("SELECT customer_id, COUNT(*) FROM account_flags WHERE status='ACTIVE' GROUP BY customer_id")
    for cust_id, count in cur.fetchall():
        flags_by_cust[cust_id] = count
    con.close()

    tier_counts = {"PLATINUM": 0, "GOLD": 0, "SILVER": 0}
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    eligible_count = 0
    flagged_count = 0

    for ecid in ecids:
        tier = crm_by_ecid.get(ecid, {}).get("tier")
        ltv = crm_by_ecid.get(ecid, {}).get("lifetime_value", 0)
        risk_info = risk_by_ecid.get(ecid, {})
        risk_rating = risk_info.get("risk_rating")
        delinquency = risk_info.get("delinquency_days", 1)
        cust_id = ECID_TO_CUST.get(ecid)
        flag_count = flags_by_cust.get(cust_id, 0)

        if tier in tier_counts:
            tier_counts[tier] += 1
        if risk_rating in risk_counts:
            risk_counts[risk_rating] += 1
        if flag_count > 0:
            flagged_count += 1

        if (
            tier in ("GOLD", "PLATINUM")
            and ltv >= 500000
            and risk_rating in ("LOW", "MEDIUM")
            and delinquency == 0
            and flag_count == 0
        ):
            eligible_count += 1

    def pct(n):
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total_customers": total,
        "eligible_count": eligible_count,
        "eligible_rate": pct(eligible_count),
        "flagged_count": flagged_count,
        "flagged_rate": pct(flagged_count),
        "risk": {
            "low": risk_counts["LOW"], "low_pct": pct(risk_counts["LOW"]),
            "medium": risk_counts["MEDIUM"], "medium_pct": pct(risk_counts["MEDIUM"]),
            "high": risk_counts["HIGH"], "high_pct": pct(risk_counts["HIGH"]),
        },
        "tier": {
            "platinum": tier_counts["PLATINUM"], "platinum_pct": pct(tier_counts["PLATINUM"]),
            "gold": tier_counts["GOLD"], "gold_pct": pct(tier_counts["GOLD"]),
            "silver": tier_counts["SILVER"], "silver_pct": pct(tier_counts["SILVER"]),
        },
    }
