"""
Policy MCP Server

Tool:
    check_fee_waiver_eligibility(customer_tier, lifetime_value, average_balance,
                                  risk_rating, delinquency_days, active_flags,
                                  mortgage_status, fee_amount)

Pure, deterministic rules -- no LLM call happens in this file. The
LLM never decides eligibility; it only explains this tool's output
in natural language afterwards.
"""
from __future__ import annotations

from mcp_servers.common.envelope import ok
from mcp_servers.common.envelope import fail  # noqa: F401 (kept for symmetry / future use)

SOURCE = "POLICY"

POLICY_ID = "FW-04"


def check_fee_waiver_eligibility(
    customer_tier: str,
    lifetime_value: float,
    average_balance: float,
    risk_rating: str,
    delinquency_days: int,
    active_flags: int,
    mortgage_payment_status: str | None,
    fee_amount: float,
) -> dict:
    reason_codes = []
    blockers = []

    tier_ok = customer_tier in ("GOLD", "PLATINUM")
    (reason_codes if tier_ok else blockers).append(
        "PREMIUM_CUSTOMER" if tier_ok else "TIER_NOT_ELIGIBLE"
    )

    ltv_ok = lifetime_value >= 500000
    (reason_codes if ltv_ok else blockers).append(
        "HIGH_CUSTOMER_VALUE" if ltv_ok else "INSUFFICIENT_CUSTOMER_VALUE"
    )

    risk_ok = risk_rating in ("LOW", "MEDIUM")
    (reason_codes if risk_ok else blockers).append(
        "ACCEPTABLE_RISK" if risk_ok else "RISK_TOO_HIGH"
    )

    delinq_ok = delinquency_days == 0
    (reason_codes if delinq_ok else blockers).append(
        "NO_DELINQUENCY" if delinq_ok else "DELINQUENCY_PRESENT"
    )

    flags_ok = active_flags == 0
    (reason_codes if flags_ok else blockers).append(
        "NO_ACTIVE_FLAGS" if flags_ok else "ACTIVE_FLAGS_PRESENT"
    )

    fee_ok = fee_amount <= 10000
    (reason_codes if fee_ok else blockers).append(
        "WITHIN_WAIVER_LIMIT" if fee_ok else "FEE_EXCEEDS_LIMIT"
    )

    if mortgage_payment_status == "LATE":
        blockers.append("MORTGAGE_PAYMENT_LATE")

    eligible = tier_ok and ltv_ok and risk_ok and delinq_ok and flags_ok and fee_ok and mortgage_payment_status != "LATE"

    return ok(
        {
            "decision": "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
            "policy": POLICY_ID,
            "reason_codes": reason_codes if eligible else blockers,
        },
        SOURCE,
    )


TOOLS = {
    "check_fee_waiver_eligibility": check_fee_waiver_eligibility,
}
