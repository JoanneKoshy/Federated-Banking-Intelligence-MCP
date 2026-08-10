"""
AP Policy MCP Server -- real MCP protocol server (stdio transport).

Wraps the deterministic business rule in tools.py; run standalone as:
    python -m mcp_servers.ap_policy.server
"""
import asyncio

from mcp.server.mcpserver import MCPServer

from mcp_servers.ap_policy import tools

server = MCPServer("ap_policy")


@server.tool()
def check_vendor_reconciliation(
    open_items: int,
    total_invoice_items: int,
    total_po_value: float,
    total_invoiced: float,
) -> dict:
    """Deterministically evaluate a vendor's invoice-to-PO reconciliation status."""
    return tools.check_vendor_reconciliation(
        open_items, total_invoice_items, total_po_value, total_invoiced,
    )


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
