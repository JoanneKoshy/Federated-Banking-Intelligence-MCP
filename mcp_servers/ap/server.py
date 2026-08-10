"""
AP MCP Server -- real MCP protocol server (stdio transport).

Wraps the business logic in tools.py; run standalone as:
    python -m mcp_servers.ap.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.ap import tools

server = MCPServer("ap")


@server.tool()
def find_vendor(name: str) -> dict:
    """Find a vendor by name and resolve their vendor ID."""
    return tools.find_vendor(name)


@server.tool()
def get_vendor_reconciliation(vendor_id: str) -> dict:
    """Get purchase order value, invoiced amount, and open items for a vendor."""
    return tools.get_vendor_reconciliation(vendor_id)


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
