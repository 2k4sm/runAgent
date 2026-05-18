"""Tool registry — maps tool names to callables."""

from typing import Any

from run_agent.tools.base import TASK_ARG_NAMES, BaseTool


class ToolRegistry:
    """Registry of available tools, keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        # Drop display-only args so they never reach `execute` (or a remote MCP server).
        for arg in TASK_ARG_NAMES:
            kwargs.pop(arg, None)
        return await tool.execute(**kwargs)
