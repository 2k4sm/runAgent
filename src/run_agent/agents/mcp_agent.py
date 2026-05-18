"""Dynamic MCP agent — built per request from selected MCP servers.

`open_mcp_tools` opens live sessions to the chosen servers and yields a
`ToolRegistry` of their tools; `MCPAgent` runs the standard ReAct loop over it.
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

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
    """A worker agent whose tools come from connected MCP servers."""

    def __init__(self, tool_registry: ToolRegistry, server_summaries: list[str]) -> None:
        super().__init__(name=AGENT_MCP, tool_registry=tool_registry)
        self._server_summaries = server_summaries

    def get_system_prompt(self) -> str:
        if not self._server_summaries:
            return MCP_AGENT_SYSTEM_PROMPT
        servers = "\n".join(self._server_summaries)
        return f"{MCP_AGENT_SYSTEM_PROMPT}\n\n## Loaded MCP servers\n\n{servers}"


@asynccontextmanager
async def open_mcp_tools(
    server_ids: list[str],
    user_id: str,
) -> AsyncGenerator[tuple[ToolRegistry, list[str], list[str]], None]:
    """Open sessions to the given servers; yield (registry, summaries, errors).

    Sessions stay open for the lifetime of the `async with` block, so the MCP
    agent can call their tools, then are closed on exit.
    """
    service = MCPServerService()
    registry = ToolRegistry()
    summaries: list[str] = []
    errors: list[str] = []

    async with AsyncExitStack() as stack:
        for server_id in server_ids:
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
                tool_names = ", ".join(t["name"] for t in tools) or "(none)"
                summaries.append(f"- {row['name']}: {tool_names}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "mcp_server_connect_failed", server=server_id, error=str(exc)
                )
                errors.append(f"{server_id}: {exc}")
        yield registry, summaries, errors
