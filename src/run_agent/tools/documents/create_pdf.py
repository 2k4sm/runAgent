"""PDF creation tool."""

import io
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from run_agent.config.constants import MIME_PDF
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import filename_with_ext, finalize


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
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=LETTER)
        styles = getSampleStyleSheet()
        flow: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

        for section in sections:
            flow.append(Paragraph(section["heading"], styles["Heading2"]))
            for paragraph in section["content"].split("\n\n"):
                if paragraph.strip():
                    flow.append(Paragraph(paragraph.strip(), styles["BodyText"]))
            flow.append(Spacer(1, 12))

        doc.build(flow)
        return await finalize(
            filename_with_ext(filename, "pdf"),
            buffer.getvalue(),
            MIME_PDF,
            _context,
        )
