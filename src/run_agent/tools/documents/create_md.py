"""Markdown creation tool."""

from typing import Any

from run_agent.config.constants import MIME_MD
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import filename_with_ext, finalize


class CreateMdTool(BaseTool):
    name = "create_md"
    description = "Create a Markdown (.md) file from raw Markdown content."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Markdown content"},
                "filename": {
                    "type": "string",
                    "description": "Output filename (without extension)",
                    "default": "document",
                },
            },
            "required": ["content"],
        }

    async def execute(
        self,
        content: str,
        filename: str = "document",
        _context: dict | None = None,
        **_kwargs: Any,
    ) -> str:
        return await finalize(
            filename_with_ext(filename, "md"),
            content.encode("utf-8"),
            MIME_MD,
            _context,
        )
