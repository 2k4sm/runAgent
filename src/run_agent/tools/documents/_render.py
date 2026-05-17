"""Shared rendering helpers.

PDFs cannot be edited in place, so both `create_pdf` and `edit_document` build
them the same way through `render_pdf`.
"""

import io
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def render_pdf(title: str, sections: list[dict[str, Any]]) -> bytes:
    """Render a titled, sectioned PDF and return its bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER)
    styles = getSampleStyleSheet()
    flow: list[Any] = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    for section in sections:
        flow.append(Paragraph(section.get("heading", ""), styles["Heading2"]))
        for paragraph in str(section.get("content", "")).split("\n\n"):
            if paragraph.strip():
                flow.append(Paragraph(paragraph.strip(), styles["BodyText"]))
        flow.append(Spacer(1, 12))

    doc.build(flow)
    return buffer.getvalue()
