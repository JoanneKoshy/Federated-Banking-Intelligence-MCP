"""
MCP Client Manager.

This is the real MCP client layer. Instead of calling Python functions
directly (the old approach), the orchestrator now talks to 6 separate
MCP server *processes* over the real MCP protocol (stdio transport),
using the official `mcp` Python SDK.

Each server is spawned once at app startup (persistent connection kept
open for the app's lifetime, not respawned per-query -- respawning per
tool call would add significant latency), and torn down on shutdown.

Usage:
    await mcp_client.start_all()   # call once at app startup
    result = await mcp_client.call_tool("crm", "find_customer", name="Sarah Jenkins")
    await mcp_client.stop_all()    # call once at app shutdown
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVERS = {
    "crm": "mcp_servers.crm.server",
    "core_banking": "mcp_servers.core_banking.server",
    "risk": "mcp_servers.risk.server",
    "policy": "mcp_servers.policy.server",
    "ap": "mcp_servers.ap.server",
    "ap_policy": "mcp_servers.ap_policy.server",
}

_sessions: dict[str, ClientSession] = {}
_exit_stack: AsyncExitStack | None = None


async def start_all() -> None:
    """Spawn all 6 MCP server processes and open persistent client sessions."""
    global _exit_stack
    _exit_stack = AsyncExitStack()

    for name, module in SERVERS.items():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", module],
            cwd=PROJECT_ROOT,
        )
        read, write = await _exit_stack.enter_async_context(stdio_client(params))
        session = await _exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        _sessions[name] = session


async def stop_all() -> None:
    """Close all MCP client sessions and terminate the server subprocesses."""
    global _exit_stack
    if _exit_stack:
        await _exit_stack.aclose()
        _exit_stack = None
    _sessions.clear()


async def call_tool(server_name: str, tool_name: str, **kwargs) -> dict:
    """
    Call a tool on a specific MCP server over the real protocol.
    Returns the same standard envelope dict the tool itself returns
    ({"success", "data", "error", "source"}).
    """
    session = _sessions.get(server_name)
    if session is None:
        return {
            "success": False,
            "data": None,
            "error": {"code": "MCP_SERVER_UNAVAILABLE", "message": f"'{server_name}' MCP server is not connected."},
            "source": server_name.upper(),
        }

    try:
        result = await session.call_tool(tool_name, kwargs)

        if result.is_error:
            error_text = result.content[0].text if result.content else "Unknown MCP tool error"
            return {
                "success": False,
                "data": None,
                "error": {"code": "TOOL_EXECUTION_ERROR", "message": error_text},
                "source": server_name.upper(),
            }

        text = result.content[0].text
        return json.loads(text)
    except Exception as exc:
        return {
            "success": False,
            "data": None,
            "error": {"code": "MCP_CALL_FAILED", "message": str(exc)},
            "source": server_name.upper(),
        }
