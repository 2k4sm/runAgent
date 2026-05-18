"""Adapts a tool exposed by an MCP server into a runAgent `BaseTool`."""

import re
from typing import Any

from run_agent.services.mcp_client import MCPClient
from run_agent.tools.base import BaseTool


def slugify(text: str) -> str:
    """Reduce a string to a safe tool-name fragment (`[A-Za-z0-9_-]`)."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_").lower() or "server"


class MCPTool(BaseTool):
    """A single MCP-server tool, callable through an open `MCPClient` session."""

    def __init__(
        self,
        client: MCPClient,
        server_slug: str,
        tool_def: dict[str, Any],
        icon_url: str | None = None,
    ) -> None:
        self._client = client
        self._original_name: str = tool_def["name"]
        # OpenAI function names must match ^[A-Za-z0-9_-]+$ and stay short.
        self.name = f"mcp_{server_slug}_{slugify(self._original_name)}"[:64]
        self.description = (
            tool_def.get("description") or f"MCP tool '{self._original_name}'"
        )
        # Live favicon URL for the owning MCP server, surfaced in `tool_call` events.
        self.icon_url = icon_url
        self._schema: dict[str, Any] = tool_def.get("input_schema") or {
            "type": "object",
            "properties": {},
        }

    def parameters_schema(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, _context: dict | None = None, **kwargs: Any) -> str:
        return await self._client.call_tool(self._original_name, kwargs)
