"""CSV creation tool."""

import csv
import io
from typing import Any

from run_agent.config.constants import MIME_CSV
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import filename_with_ext, finalize


class CreateCsvTool(BaseTool):
    name = "create_csv"
    description = "Create a CSV file from a header row and data rows."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column header names",
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "Data rows",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (without extension)",
                    "default": "data",
                },
            },
            "required": ["headers", "rows"],
        }

    async def execute(
        self,
        headers: list[str],
        rows: list[list[str]],
        filename: str = "data",
        _context: dict | None = None,
        **_kwargs: Any,
    ) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return await finalize(
            filename_with_ext(filename, "csv"),
            buffer.getvalue().encode("utf-8"),
            MIME_CSV,
            _context,
        )
