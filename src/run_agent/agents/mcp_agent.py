"""Specialized MCP agent — one per connected MCP server, built on demand.

`open_mcp_tools` opens a live session to a single server and yields a
`ToolRegistry` of just that server's tools; `MCPAgent` runs the standard ReAct
loop over it, grounded in that server's description.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from run_agent.agents.base import BaseAgent
from run_agent.config.constants import AGENT_MCP
from run_agent.config.logging import get_logger
from run_agent.prompts.mcp import MCP_AGENT_SYSTEM_PROMPT
from run_agent.services.mcp_client import MCPClient
from run_agent.services.mcp_service import MCPServerService
from run_agent.tools.mcp.mcp_tool import MCPTool, slugify
from run_agent.tools.registry import ToolRegistry
from run_agent.utils.favicon import favicon_url

logger = get_logger(__name__)


class MCPAgent(BaseAgent):
    """A worker agent specialized to one connected MCP server."""

    def __init__(self, tool_registry: ToolRegistry, server_info: dict[str, Any]) -> None:
        # Identify the agent by its server's name so the UI shows e.g.
        # "Linear response" rather than a generic "Mcp response".
        super().__init__(
            name=server_info.get("name") or AGENT_MCP,
            tool_registry=tool_registry,
        )
        self._server_info = server_info

    def get_system_prompt(self) -> str:
        info = self._server_info
        lines = [
            MCP_AGENT_SYSTEM_PROMPT,
            "",
            f"## Server: {info.get('name') or 'the connected server'}",
        ]
        if info.get("description"):
            lines.append(info["description"])
        tool_names = ", ".join(t.get("name", "") for t in (info.get("tools") or []))
        if tool_names:
            lines.append(f"\nAvailable tools: {tool_names}")
        return "\n".join(lines)


@asynccontextmanager
async def open_mcp_tools(
    server_id: str,
    user_id: str,
) -> AsyncGenerator[tuple[ToolRegistry, list[str]], None]:
    """Open a session to one server; yield (registry, errors).

    The session stays open for the lifetime of the `async with` block, so the
    MCP agent can call the server's tools, then is closed on exit.
    """
    service = MCPServerService()
    registry = ToolRegistry()
    errors: list[str] = []

    async with AsyncExitStack() as stack:
        try:
            row = await service.get_row(server_id, user_id)
            headers = await service.resolve_headers(row)
            client = await stack.enter_async_context(
                MCPClient(row["url"], headers, row["transport"])
            )
            tools = await client.list_tools()
            slug = slugify(row["name"])
            icon_url = favicon_url(row["url"])
            for tool_def in tools:
                registry.register(MCPTool(client, slug, tool_def, icon_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_server_connect_failed", server=server_id, error=str(exc))
            errors.append(f"{server_id}: {exc}")
        yield registry, errors
