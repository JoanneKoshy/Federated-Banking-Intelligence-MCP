from __future__ import annotations

from typing import Any, TypedDict


class TraceStep(TypedDict):
    sequence: int
    mcp_server: str
    tool: str
    input: dict
    output_summary: Any
    status: str  # SUCCESS | FAILURE
    error: str | None
    duration_ms: float


class BankingAgentState(TypedDict, total=False):
    query: str
    intent: str
    customer_name: str | None
    fee_amount: float
    enterprise_customer_id: str | None
    evidence: dict
    policy_result: dict | None
    trace: list
    status: str  # OK | NO_DECISION | REJECTED
    error: str | None
    final_message: str
