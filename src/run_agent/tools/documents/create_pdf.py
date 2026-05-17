"""PDF creation tool."""

from typing import Any

from run_agent.config.constants import MIME_PDF
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import filename_with_ext, finalize
from run_agent.tools.documents._render import render_pdf


class CreatePdfTool(BaseTool):
    name = "create_pdf"
    description = "Create a PDF document with a title and formatted sections."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["heading", "content"],
                    },
                    "description": "Document sections with headings and content",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (without extension)",
                    "default": "document",
                },
            },
            "required": ["title", "sections"],
        }

    async def execute(
        self,
        title: str,
        sections: list[dict],
        filename: str = "document",
        _context: dict | None = None,
        **_kwargs: Any,
    ) -> str:
        return await finalize(
            filename_with_ext(filename, "pdf"),
            render_pdf(title, sections),
            MIME_PDF,
            _context,
        )
