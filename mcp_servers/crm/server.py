"""
CRM MCP Server -- real MCP protocol server (stdio transport).

Wraps the business logic in tools.py; run standalone as:
    python -m mcp_servers.crm.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.crm import tools

server = MCPServer("crm")


@server.tool()
def find_customer(name: str) -> dict:
    """Find a customer by name and resolve their Enterprise Customer ID."""
    return tools.find_customer(name)


@server.tool()
def get_customer_value(enterprise_customer_id: str) -> dict:
    """Get CRM tier, lifetime value, and relationship info for a customer."""
    return tools.get_customer_value(enterprise_customer_id)


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
