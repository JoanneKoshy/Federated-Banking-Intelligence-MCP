"""
Risk MCP Server -- real MCP protocol server (stdio transport).

Wraps the business logic in tools.py; run standalone as:
    python -m mcp_servers.risk.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.risk import tools

server = MCPServer("risk")


@server.tool()
def get_credit_risk(enterprise_customer_id: str) -> dict:
    """Get credit risk rating and score for a customer."""
    return tools.get_credit_risk(enterprise_customer_id)


@server.tool()
def get_mortgage_status(enterprise_customer_id: str) -> dict:
    """Get mortgage payment status for a customer."""
    return tools.get_mortgage_status(enterprise_customer_id)


@server.tool()
def set_availability(available: bool) -> dict:
    """Admin tool: toggle this server's simulated availability, for the fail-closed demo scenario."""
    tools.set_availability(available)
    return {"success": True, "data": {"available": available}, "error": None, "source": "RISK"}


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
