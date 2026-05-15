"""XLSX creation tool."""

import io
from typing import Any

from openpyxl import Workbook

from run_agent.config.constants import MIME_XLSX
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import filename_with_ext, finalize


class CreateXlsxTool(BaseTool):
    name = "create_xlsx"
    description = "Create an Excel spreadsheet (.xlsx) with one or more sheets."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {
                                "type": "array",
                                "items": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                        "required": ["name", "headers", "rows"],
                    },
                    "description": "Sheets, each with a name, header row, and data rows",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (without extension)",
                    "default": "spreadsheet",
                },
            },
            "required": ["sheets"],
        }

    async def execute(
        self,
        sheets: list[dict],
        filename: str = "spreadsheet",
        _context: dict | None = None,
        **_kwargs: Any,
    ) -> str:
        workbook = Workbook()
        workbook.remove(workbook.active)  # drop the default sheet

        for sheet in sheets:
            worksheet = workbook.create_sheet(title=sheet["name"][:31])
            worksheet.append(list(sheet["headers"]))
            for row in sheet["rows"]:
                worksheet.append(list(row))

        buffer = io.BytesIO()
        workbook.save(buffer)
        return await finalize(
            filename_with_ext(filename, "xlsx"),
            buffer.getvalue(),
            MIME_XLSX,
            _context,
        )
