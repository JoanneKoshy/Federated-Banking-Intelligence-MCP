"""
Policy MCP Server -- real MCP protocol server (stdio transport).

Wraps the deterministic business rule in tools.py; run standalone as:
    python -m mcp_servers.policy.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.policy import tools

server = MCPServer("policy")


@server.tool()
def check_fee_waiver_eligibility(
    customer_tier: str,
    lifetime_value: float,
    average_balance: float,
    risk_rating: str,
    delinquency_days: int,
    active_flags: int,
    mortgage_payment_status: str,
    fee_amount: float,
) -> dict:
    """Deterministically evaluate fee-waiver eligibility for a customer."""
    return tools.check_fee_waiver_eligibility(
        customer_tier, lifetime_value, average_balance, risk_rating,
        delinquency_days, active_flags, mortgage_payment_status, fee_amount,
    )


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
