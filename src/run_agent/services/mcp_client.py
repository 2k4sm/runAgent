"""Thin wrapper around the MCP SDK for connecting to remote MCP servers.

`MCPClient` is an async context manager: it opens a session (auto-detecting the
transport — Streamable HTTP, then SSE) and keeps it open so an agent can make
several `call_tool` calls before it closes.
"""

import json
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from run_agent.config.logging import get_logger

logger = get_logger(__name__)


class MCPConnectionError(Exception):
    """Raised when an MCP server cannot be reached or initialized."""


def _result_text(result: Any) -> str:
    """Flatten a CallToolResult into a string for the LLM."""
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    structured = getattr(result, "structuredContent", None)
    if not parts and structured is not None:
        parts.append(json.dumps(structured))
    body = "\n".join(parts) or "(no content)"
    if getattr(result, "isError", False):
        return f"Error from MCP tool: {body}"
    return body


class MCPClient:
    """An open connection to one MCP server."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        transport: str = "auto",
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.transport = transport
        self.detected_transport: str | None = None
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "MCPClient":
        transports = (
            ["streamable_http", "sse"]
            if self.transport == "auto"
            else [self.transport]
        )
        last_error: Exception | None = None
        for transport in transports:
            stack = AsyncExitStack()
            try:
                session = await self._connect(stack, transport)
                await session.initialize()
                self._stack = stack
                self._session = session
                self.detected_transport = transport
                return self
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await stack.aclose()
        raise MCPConnectionError(
            f"Could not connect to MCP server at {self.url}: {last_error}"
        )

    async def __aexit__(self, *_exc: object) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def _connect(self, stack: AsyncExitStack, transport: str) -> ClientSession:
        if transport == "streamable_http":
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(self.url, headers=self.headers)
            )
        else:
            read, write = await stack.enter_async_context(
                sse_client(self.url, headers=self.headers)
            )
        return await stack.enter_async_context(ClientSession(read, write))

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise MCPConnectionError("MCP session is not open")
        return self._session

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return the server's tools as `{name, description, input_schema}`."""
        result = await self.session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema
                or {"type": "object", "properties": {}},
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one tool and return its result as text."""
        result = await self.session.call_tool(name, arguments)
        return _result_text(result)
