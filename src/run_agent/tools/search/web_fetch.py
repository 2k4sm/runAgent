"""URL content extraction tool.

Note: HTML-to-text here is a simple regex strip. For higher-quality extraction,
swap in `trafilatura` (tracked as a follow-up).
"""

import re
from typing import Any

import httpx

from run_agent.tools.base import BaseTool

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and extract the main text content from a URL."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch content from"},
            },
            "required": ["url"],
        }

    async def execute(self, url: str, **_kwargs: Any) -> str:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "runAgent/1.0"})
            response.raise_for_status()

        text = _TAG_RE.sub(" ", response.text)
        text = _WS_RE.sub(" ", text).strip()
        return text[:8000]
