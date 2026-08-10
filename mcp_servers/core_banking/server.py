"""
Core Banking MCP Server -- real MCP protocol server (stdio transport).

Wraps the business logic in tools.py; run standalone as:
    python -m mcp_servers.core_banking.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.core_banking import tools

server = MCPServer("core_banking")


@server.tool()
def get_customer_account_summary(enterprise_customer_id: str) -> dict:
    """Get account balances for a customer."""
    return tools.get_customer_account_summary(enterprise_customer_id)


@server.tool()
def get_transaction_summary(enterprise_customer_id: str, days: int = 90) -> dict:
    """Get average balance over a recent transaction window."""
    return tools.get_transaction_summary(enterprise_customer_id, days)


@server.tool()
def get_customer_flags(enterprise_customer_id: str) -> dict:
    """Get active account flags for a customer."""
    return tools.get_customer_flags(enterprise_customer_id)


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
