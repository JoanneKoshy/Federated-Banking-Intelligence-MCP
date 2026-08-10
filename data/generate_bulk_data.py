"""
Generates ~100 synthetic customers and seeds them into:
    - Postgres (CRM domain)         -- requires DATABASE_URL in .env
    - data/credit_risk.csv, data/loans.csv (Risk domain)
    - data/core_banking.db (Core Banking fallback, used only when SAP is off)
    - mcp_servers/common/identity_data.json (the ECID <-> per-system ID map)

Run with:  python data/generate_bulk_data.py
Re-run any time to regenerate a fresh dataset (deterministic, seeded RNG).
"""
from __future__ import annotations

import csv
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

import psycopg2
from dotenv import load_dotenv

load_dotenv()

random.seed(42)  # deterministic -- same dataset every run, easier to demo reliably

HERE = os.path.dirname(os.path.abspath(__file__))
N_CUSTOMERS = 100

FIRST_NAMES = [
    "Sarah", "Robert", "Priya", "David", "Michael", "Anjali", "James", "Fatima",
    "Daniel", "Meera", "William", "Aisha", "Thomas", "Kavya", "Richard", "Zara",
    "Arjun", "Emma", "Rahul", "Olivia", "Vikram", "Sophia", "Karan", "Ananya",
    "John", "Divya", "Christopher", "Neha", "Matthew", "Isha", "Rohan", "Grace",
    "Aditya", "Chloe", "Nikhil", "Maya", "Andrew", "Riya", "Joseph", "Tara",
]
LAST_NAMES = [
    "Jenkins", "Miller", "Nair", "Wilson", "Anderson", "Sharma", "Clark", "Khan",
    "Patel", "Reddy", "Brown", "Ahmed", "White", "Gupta", "Taylor", "Malik",
    "Rao", "Davis", "Iyer", "Moore", "Singh", "Wright", "Verma", "Menon",
    "Mehta", "Kapoor", "Joshi", "Bose", "Chatterjee", "Roy", "Das", "Kumar",
]

TIER_WEIGHTS = [("PLATINUM", 0.25), ("GOLD", 0.35), ("SILVER", 0.40)]
RISK_WEIGHTS = [("LOW", 0.55), ("MEDIUM", 0.30), ("HIGH", 0.15)]


def weighted_choice(weights):
    r = random.random()
    cum = 0.0
    for value, w in weights:
        cum += w
        if r <= cum:
            return value
    return weights[-1][0]


# These 4 are pinned to their original values so existing demo buttons,
# scripts, and tests keep working exactly as before after scaling up.
PINNED_CUSTOMERS = [
    {"ecid": "ECID-00001", "cust_id": "CUST-10023", "crm_id": "CRM-78321", "risk_id": "RISK-9921",
     "name": "Sarah Jenkins", "tier": "PLATINUM", "lifetime_value": 1840000, "annual_revenue": 175000,
     "products_held": 5, "customer_score": 92, "risk_rating": "LOW", "credit_score": 785,
     "total_exposure": 4200000, "delinquency_days": 0, "savings_balance": 920000,
     "credit_card_balance": -45000, "available_credit": 355000, "has_flag": False, "flag_type": None,
     "has_mortgage": True, "mortgage_status": "CURRENT", "mortgage_outstanding": 4200000},
    {"ecid": "ECID-00002", "cust_id": "CUST-10024", "crm_id": "CRM-78322", "risk_id": "RISK-9922",
     "name": "Robert Miller", "tier": "GOLD", "lifetime_value": 620000, "annual_revenue": 90000,
     "products_held": 3, "customer_score": 74, "risk_rating": "HIGH", "credit_score": 610,
     "total_exposure": 3100000, "delinquency_days": 45, "savings_balance": 150000,
     "credit_card_balance": -120000, "available_credit": 30000, "has_flag": False, "flag_type": None,
     "has_mortgage": True, "mortgage_status": "LATE", "mortgage_outstanding": 3100000},
    {"ecid": "ECID-00003", "cust_id": "CUST-10025", "crm_id": "CRM-78323", "risk_id": "RISK-9923",
     "name": "Priya Nair", "tier": "PLATINUM", "lifetime_value": 980000, "annual_revenue": 110000,
     "products_held": 4, "customer_score": 81, "risk_rating": "MEDIUM", "credit_score": 690,
     "total_exposure": 1800000, "delinquency_days": 0, "savings_balance": 610000,
     "credit_card_balance": -18000, "available_credit": 82000, "has_flag": True,
     "flag_type": "SUSPICIOUS_ACTIVITY", "has_mortgage": True, "mortgage_status": "CURRENT",
     "mortgage_outstanding": 600000},
    {"ecid": "ECID-00004", "cust_id": "CUST-10026", "crm_id": "CRM-78324", "risk_id": "RISK-9924",
     "name": "David Wilson", "tier": "SILVER", "lifetime_value": 210000, "annual_revenue": 40000,
     "products_held": 1, "customer_score": 55, "risk_rating": "LOW", "credit_score": 700,
     "total_exposure": 500000, "delinquency_days": 0, "savings_balance": 95000,
     "credit_card_balance": -8000, "available_credit": 12000, "has_flag": False, "flag_type": None,
     "has_mortgage": True, "mortgage_status": "CURRENT", "mortgage_outstanding": 500000},
]


def generate_customers(n: int) -> list[dict]:
    customers = list(PINNED_CUSTOMERS)
    used_names = {c["name"] for c in PINNED_CUSTOMERS}
    for i in range(len(PINNED_CUSTOMERS) + 1, n + 1):
        while True:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break

        # offset ranges well clear of the pinned customers' hand-picked IDs
        ecid = f"ECID-{i:05d}"
        cust_id = f"CUST-{20000 + i}"
        crm_id = f"CRM-{80000 + i}"
        risk_id = f"RISK-{15000 + i}"

        tier = weighted_choice(TIER_WEIGHTS)
        risk_rating = weighted_choice(RISK_WEIGHTS)

        ltv_base = {"PLATINUM": 1_500_000, "GOLD": 700_000, "SILVER": 250_000}[tier]
        lifetime_value = round(ltv_base * random.uniform(0.7, 1.6), -3)
        annual_revenue = round(lifetime_value * random.uniform(0.08, 0.15), -3)
        products_held = random.randint(1, 6)
        customer_score = random.randint(50, 98)

        credit_score = {
            "LOW": random.randint(740, 820),
            "MEDIUM": random.randint(660, 739),
            "HIGH": random.randint(560, 659),
        }[risk_rating]
        total_exposure = round(random.uniform(200_000, 5_000_000), -3)
        # ~85% of customers have zero delinquency; rest have some
        delinquency_days = 0 if random.random() < 0.85 else random.choice([15, 30, 45, 60])

        savings_balance = round(random.uniform(50_000, 1_200_000), -3)
        credit_card_balance = -round(random.uniform(5_000, 150_000), -3)
        available_credit = round(random.uniform(20_000, 400_000), -3)

        # ~90% of customers have no active flags
        has_flag = random.random() > 0.90
        flag_type = random.choice(["SUSPICIOUS_ACTIVITY", "DISPUTE_PENDING", "KYC_REVIEW"]) if has_flag else None

        has_mortgage = random.random() < 0.6
        mortgage_status = None
        mortgage_outstanding = 0
        if has_mortgage:
            mortgage_status = "CURRENT" if delinquency_days == 0 or random.random() < 0.8 else "LATE"
            mortgage_outstanding = round(random.uniform(500_000, 6_000_000), -3)

        customers.append({
            "ecid": ecid, "cust_id": cust_id, "crm_id": crm_id, "risk_id": risk_id,
            "name": name, "tier": tier,
            "lifetime_value": lifetime_value, "annual_revenue": annual_revenue,
            "products_held": products_held, "customer_score": customer_score,
            "risk_rating": risk_rating, "credit_score": credit_score,
            "total_exposure": total_exposure, "delinquency_days": delinquency_days,
            "savings_balance": savings_balance, "credit_card_balance": credit_card_balance,
            "available_credit": available_credit,
            "has_flag": has_flag, "flag_type": flag_type,
            "has_mortgage": has_mortgage, "mortgage_status": mortgage_status,
            "mortgage_outstanding": mortgage_outstanding,
        })
    return customers


def write_identity_map(customers: list[dict]):
    name_to_ecid = {c["name"].lower(): c["ecid"] for c in customers}
    ecid_to_cust = {c["ecid"]: c["cust_id"] for c in customers}
    ecid_to_crm = {c["ecid"]: c["crm_id"] for c in customers}
    ecid_to_risk = {c["ecid"]: c["risk_id"] for c in customers}

    out_path = os.path.join(HERE, "..", "mcp_servers", "common", "identity_data.json")
    with open(out_path, "w") as f:
        json.dump({
            "name_to_ecid": name_to_ecid,
            "ecid_to_cust": ecid_to_cust,
            "ecid_to_crm": ecid_to_crm,
            "ecid_to_risk": ecid_to_risk,
        }, f, indent=2)
    print(f"wrote {out_path} ({len(customers)} customers)")


def seed_postgres_crm(customers: list[dict]):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS customer_value")
    cur.execute("DROP TABLE IF EXISTS customer_profile")
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
            crm_customer_id TEXT PRIMARY KEY REFERENCES customer_profile(crm_customer_id),
            lifetime_value NUMERIC,
            annual_revenue NUMERIC,
            products_held INTEGER,
            customer_score INTEGER,
            last_calculated TEXT
        )
    """)
    for c in customers:
        cur.execute(
            "INSERT INTO customer_profile VALUES (%s,%s,%s,%s,%s,%s)",
            (c["crm_id"], c["ecid"], c["name"], c["tier"], "2020-01-01", "Anita Sharma"),
        )
        cur.execute(
            "INSERT INTO customer_value VALUES (%s,%s,%s,%s,%s,%s)",
            (c["crm_id"], c["lifetime_value"], c["annual_revenue"], c["products_held"], c["customer_score"], "2026-08-01"),
        )
    conn.commit()
    cur.close()
    conn.close()
    print(f"seeded Postgres CRM tables ({len(customers)} customers)")


def seed_risk_csv(customers: list[dict]):
    risk_path = os.path.join(HERE, "credit_risk.csv")
    loans_path = os.path.join(HERE, "loans.csv")

    with open(risk_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["risk_customer_id", "enterprise_customer_id", "risk_rating", "credit_score", "total_exposure", "delinquency_days", "last_assessment"])
        for c in customers:
            w.writerow([c["risk_id"], c["ecid"], c["risk_rating"], c["credit_score"], c["total_exposure"], c["delinquency_days"], "2026-08-01"])

    with open(loans_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["loan_id", "risk_customer_id", "loan_type", "original_amount", "outstanding_amount", "monthly_payment", "status", "payment_status"])
        loan_seq = 90000
        for c in customers:
            if c["has_mortgage"]:
                loan_seq += 1
                w.writerow([f"LN-{loan_seq}", c["risk_id"], "MORTGAGE", round(c["mortgage_outstanding"] * 1.3, -3), c["mortgage_outstanding"], round(c["mortgage_outstanding"] * 0.012, -2), "ACTIVE", c["mortgage_status"]])

    print(f"seeded {risk_path} and {loans_path} ({len(customers)} customers)")


def seed_core_banking_sqlite(customers: list[dict]):
    path = os.path.join(HERE, "core_banking.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""CREATE TABLE customers (customer_id TEXT PRIMARY KEY, enterprise_customer_id TEXT, full_name TEXT, dob TEXT, status TEXT, created_date TEXT)""")
    cur.execute("""CREATE TABLE accounts (account_id TEXT PRIMARY KEY, customer_id TEXT, account_type TEXT, currency TEXT, current_balance REAL, available_balance REAL, status TEXT, opened_date TEXT)""")
    cur.execute("""CREATE TABLE transactions (transaction_id TEXT PRIMARY KEY, account_id TEXT, transaction_date TEXT, transaction_type TEXT, amount REAL, description TEXT, balance_after REAL)""")
    cur.execute("""CREATE TABLE account_flags (flag_id TEXT PRIMARY KEY, customer_id TEXT, flag_type TEXT, severity TEXT, status TEXT, created_date TEXT, description TEXT)""")

    for c in customers:
        cur.execute("INSERT INTO customers VALUES (?,?,?,?,?,?)", (c["cust_id"], c["ecid"], c["name"], "1985-01-01", "ACTIVE", "2020-01-01"))

        sav_id = f"ACC-{c['cust_id']}-S"
        cc_id = f"ACC-{c['cust_id']}-C"
        cur.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?)", (sav_id, c["cust_id"], "SAVINGS", "INR", c["savings_balance"], c["savings_balance"] * 0.97, "ACTIVE", "2020-01-01"))
        cur.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?)", (cc_id, c["cust_id"], "CREDIT_CARD", "INR", c["credit_card_balance"], c["available_credit"], "ACTIVE", "2020-01-01"))

        running = c["savings_balance"]
        base_date = datetime(2026, 1, 1)
        for i in range(6):
            amt = random.choice([4000, -2500, 6000, -3200])
            running -= amt
            cur.execute(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?)",
                (f"TXN-{sav_id}-{i}", sav_id, (base_date + timedelta(days=i * 25)).strftime("%Y-%m-%d"), "CREDIT" if amt > 0 else "DEBIT", amt, "Synthetic transaction", running),
            )

        if c["has_flag"]:
            cur.execute(
                "INSERT INTO account_flags VALUES (?,?,?,?,?,?,?)",
                (f"FLAG-{c['cust_id']}", c["cust_id"], c["flag_type"], "MEDIUM", "ACTIVE", "2026-06-01", "Auto-generated synthetic flag for demo variety"),
            )

    con.commit()
    con.close()
    print(f"seeded {path} ({len(customers)} customers)")


if __name__ == "__main__":
    customers = generate_customers(N_CUSTOMERS)
    write_identity_map(customers)
    seed_risk_csv(customers)
    seed_core_banking_sqlite(customers)
    seed_postgres_crm(customers)  # do this last, needs network/DATABASE_URL

    eligible_preview = [c["name"] for c in customers if c["tier"] in ("GOLD", "PLATINUM") and c["lifetime_value"] >= 500000 and c["risk_rating"] in ("LOW", "MEDIUM") and c["delinquency_days"] == 0 and not c["has_flag"]][:5]
    print(f"\nDone. {len(customers)} customers generated.")
    print(f"Example likely-eligible customers: {eligible_preview}")
