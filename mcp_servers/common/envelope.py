"""
Standard MCP tool response envelope.

Every tool across every MCP server (Core Banking, CRM, Risk, Policy)
returns this exact shape. This is what makes the orchestrator's
retrieval/validation logic generic instead of one-off per tool.

    Success -> {"success": True,  "data": {...}, "error": None, "source": "CRM"}
    Failure -> {"success": False, "data": None,  "error": {"code": ..., "message": ...}, "source": "CRM"}
"""
from __future__ import annotations

from typing import Any, Optional


def ok(data: Any, source: str) -> dict:
    return {"success": True, "data": data, "error": None, "source": source}


def fail(code: str, message: str, source: str) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message},
        "source": source,
    }


class ToolError(Exception):
    """Raise inside a tool implementation to produce a `fail(...)` envelope."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
