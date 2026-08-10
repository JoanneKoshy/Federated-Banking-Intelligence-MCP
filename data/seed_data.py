"""
Generates the synthetic data for the POC.

Data sources today (all fake, safe to regenerate any time):
    data/crm.db              -> SQLite, stands in for CRM
    data/credit_risk.csv      -> Risk ratings
    data/loans.csv            -> Mortgage / loan status
    data/core_banking.db      -> SQLite, stands in for Core Banking

SAP SWAP POINT
---------------
`data/core_banking.db` is the one source designed to be swapped for a
real SAP BTP-backed store later. Today the Core Banking MCP server
(mcp_servers/core_banking/tools.py) reads from this SQLite file.
When the SAP sandbox is ready, replace the repository functions in
that file with calls to the SAP BTP service/OData endpoint --
nothing else in the orchestrator, policy engine, or frontend needs to
change, because they only ever see the standard tool envelope.

Run:  python data/seed_data.py
"""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

CUSTOMERS = [
    # ecid, cust_id, crm_id, risk_id, name, dob
    ("ECID-00001", "CUST-10023", "CRM-78321", "RISK-9921", "Sarah Jenkins", "1982-04-18"),
    ("ECID-00002", "CUST-10024", "CRM-78322", "RISK-9922", "Robert Miller", "1975-11-02"),
    ("ECID-00003", "CUST-10025", "CRM-78323", "RISK-9923", "Priya Nair", "1990-06-30"),
    ("ECID-00004", "CUST-10026", "CRM-78324", "RISK-9924", "David Wilson", "1988-01-14"),
]


def seed_core_banking():
    path = os.path.join(HERE, "core_banking.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE customers (
            customer_id TEXT PRIMARY KEY,
            enterprise_customer_id TEXT,
            full_name TEXT,
            dob TEXT,
            status TEXT,
            created_date TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE accounts (
            account_id TEXT PRIMARY KEY,
            customer_id TEXT,
            account_type TEXT,
            currency TEXT,
            current_balance REAL,
            available_balance REAL,
            status TEXT,
            opened_date TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE transactions (
            transaction_id TEXT PRIMARY KEY,
            account_id TEXT,
            transaction_date TEXT,
            transaction_type TEXT,
            amount REAL,
            description TEXT,
            balance_after REAL
        )
    """)
    cur.execute("""
        CREATE TABLE account_flags (
            flag_id TEXT PRIMARY KEY,
            customer_id TEXT,
            flag_type TEXT,
            severity TEXT,
            status TEXT,
            created_date TEXT,
            description TEXT
        )
    """)

    accounts = {
        "CUST-10023": [("ACC-10001", "SAVINGS", 920000, 900000), ("ACC-10002", "CREDIT_CARD", -45000, 355000)],
        "CUST-10024": [("ACC-10003", "SAVINGS", 150000, 140000), ("ACC-10002B", "CREDIT_CARD", -120000, 30000)],
        "CUST-10025": [("ACC-10004", "SAVINGS", 610000, 600000), ("ACC-10002C", "CREDIT_CARD", -18000, 82000)],
        "CUST-10026": [("ACC-10005", "SAVINGS", 95000, 90000), ("ACC-10002D", "CREDIT_CARD", -8000, 12000)],
    }

    for ecid, cust_id, crm_id, risk_id, name, dob in CUSTOMERS:
        cur.execute(
            "INSERT INTO customers VALUES (?,?,?,?,?,?)",
            (cust_id, ecid, name, dob, "ACTIVE", "2014-03-01"),
        )
        for acc_id, acc_type, bal, avail in accounts[cust_id]:
            cur.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?)",
                (acc_id, cust_id, acc_type, "INR", bal, avail, "ACTIVE", "2014-03-01"),
            )
            # ~6 months of light synthetic transaction history
            running = bal
            base_date = datetime(2026, 1, 1)
            for i in range(12):
                amt = 5000 if i % 2 == 0 else -3200
                running -= amt
                cur.execute(
                    "INSERT INTO transactions VALUES (?,?,?,?,?,?,?)",
                    (
                        f"TXN-{acc_id}-{i}",
                        acc_id,
                        (base_date + timedelta(days=i * 15)).strftime("%Y-%m-%d"),
                        "CREDIT" if amt > 0 else "DEBIT",
                        amt,
                        "Synthetic transaction",
                        running,
                    ),
                )

    # Only Priya Nair has an active flag (drives the "not eligible" demo path)
    cur.execute(
        "INSERT INTO account_flags VALUES (?,?,?,?,?,?,?)",
        ("FLAG-001", "CUST-10025", "SUSPICIOUS_ACTIVITY", "MEDIUM", "ACTIVE", "2026-06-01", "Unusual transaction pattern flagged for review"),
    )

    con.commit()
    con.close()
    print(f"seeded {path}")


def seed_crm():
    path = os.path.join(HERE, "crm.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE customer_profile (
            crm_customer_id TEXT PRIMARY KEY,
            enterprise_customer_id TEXT,
            full_name TEXT,
            customer_segment TEXT,
            relationship_since TEXT,
            relationship_manager TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE customer_value (
            crm_customer_id TEXT PRIMARY KEY,
            lifetime_value REAL,
            annual_revenue REAL,
            products_held INTEGER,
            customer_score INTEGER,
            last_calculated TEXT
        )
    """)

    profiles = {
        "ECID-00001": ("PLATINUM", "2014-05-01", "Anita Sharma", 1840000, 175000, 5, 92),
        "ECID-00002": ("GOLD", "2016-02-11", "Anita Sharma", 620000, 90000, 3, 74),  # high risk -> not eligible
        "ECID-00003": ("PLATINUM", "2018-09-20", "Anita Sharma", 980000, 110000, 4, 81),  # active flag -> not eligible
        "ECID-00004": ("SILVER", "2021-01-05", "Anita Sharma", 210000, 40000, 1, 55),  # low LTV -> not eligible
    }

    for ecid, cust_id, crm_id, risk_id, name, dob in CUSTOMERS:
        seg, since, rm, ltv, rev, products, score = profiles[ecid]
        cur.execute(
            "INSERT INTO customer_profile VALUES (?,?,?,?,?,?)",
            (crm_id, ecid, name, seg, since, rm),
        )
        cur.execute(
            "INSERT INTO customer_value VALUES (?,?,?,?,?,?)",
            (crm_id, ltv, rev, products, score, "2026-07-20"),
        )

    con.commit()
    con.close()
    print(f"seeded {path}")


def seed_risk():
    risk_path = os.path.join(HERE, "credit_risk.csv")
    loans_path = os.path.join(HERE, "loans.csv")

    risk_rows = {
        "ECID-00001": ("RISK-9921", "LOW", 785, 4200000, 0, "2026-07-15"),
        "ECID-00002": ("RISK-9922", "HIGH", 610, 3100000, 45, "2026-07-15"),
        "ECID-00003": ("RISK-9923", "MEDIUM", 690, 1800000, 0, "2026-07-15"),
        "ECID-00004": ("RISK-9924", "LOW", 700, 500000, 0, "2026-07-15"),
    }
    with open(risk_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["risk_customer_id", "enterprise_customer_id", "risk_rating", "credit_score", "total_exposure", "delinquency_days", "last_assessment"])
        for ecid, (risk_id, rating, score, exposure, delinq, date) in risk_rows.items():
            w.writerow([risk_id, ecid, rating, score, exposure, delinq, date])

    loan_rows = [
        ("LN-88721", "RISK-9921", "MORTGAGE", 5500000, 4200000, 48000, "ACTIVE", "CURRENT"),
        ("LN-88722", "RISK-9922", "MORTGAGE", 3800000, 3100000, 32000, "ACTIVE", "LATE"),
        ("LN-88723", "RISK-9923", "PERSONAL", 900000, 600000, 15000, "ACTIVE", "CURRENT"),
        ("LN-88724", "RISK-9924", "MORTGAGE", 1200000, 500000, 9000, "ACTIVE", "CURRENT"),
    ]
    with open(loans_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loan_id", "risk_customer_id", "loan_type", "original_amount", "outstanding_amount", "monthly_payment", "status", "payment_status"])
        for row in loan_rows:
            w.writerow(row)

    print(f"seeded {risk_path}")
    print(f"seeded {loans_path}")


if __name__ == "__main__":
    seed_core_banking()
    seed_crm()
    seed_risk()
    print("\nAll synthetic data sources seeded.")
    print("Customers: Sarah Jenkins (eligible), Robert Miller (high risk),")
    print("Priya Nair (active flag), David Wilson (low LTV). Michael Anderson does not exist.")
