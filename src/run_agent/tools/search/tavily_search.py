"""Tavily web search tool."""

from typing import Any

from tavily import AsyncTavilyClient

from run_agent.config.settings import settings
from run_agent.tools.base import BaseTool


class TavilySearchTool(BaseTool):
    name = "tavily_search"
    description = "Search the web for current information on any topic."

    def __init__(self) -> None:
        self.client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(  # noqa: ANN003
        self,
        query: str,
        max_results: int = 5,
        **_kwargs: Any,
    ) -> str:
        results = await self.client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_answer=True,
        )

        parts: list[str] = []
        if results.get("answer"):
            parts.append(f"Summary: {results['answer']}\n")

        for i, result in enumerate(results.get("results", []), 1):
            parts.append(
                f"{i}. [{result['title']}]({result['url']})\n"
                f"   {result.get('content', 'No content available')}\n"
            )

        return "\n".join(parts) or "No results found."
