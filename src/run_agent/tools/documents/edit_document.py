"""Apply targeted edits to an existing document, saving a new version."""

import json
from typing import Any

from run_agent.services.file_service import FileService
from run_agent.tools.base import BaseTool
from run_agent.tools.documents._common import next_version_name
from run_agent.tools.documents._edit_ops import apply_edits


class EditDocumentTool(BaseTool):
    name = "edit_document"
    description = (
        "Make TARGETED edits to an existing document — change only the sections "
        "or cells the user asked about, leaving everything else untouched. Saves "
        "the result as a new version (e.g. report.docx -> report-v2.docx). "
        "Use list_documents to find the asset_id and read_document to see the "
        "current structure before editing. Do NOT recreate the whole document."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "The asset_id of the document to edit.",
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "Ordered list of targeted edit operations. Each item is an "
                        "object with an 'op' field. Supported ops: "
                        "replace_section {heading, content}; "
                        "add_section {heading, content, after}; "
                        "remove_section {heading}; "
                        "set_title {title}; "
                        "replace_text {find, replace}; "
                        "set_cell {sheet, cell, value} (spreadsheets); "
                        "add_row {sheet, values} / remove_row {sheet, row} "
                        "(spreadsheets/CSV). For DOCX/PDF a 'section' is a heading; "
                        "for PPTX a 'section' is a slide matched by its title."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["asset_id", "operations"],
        }

    async def execute(
        self,
        asset_id: str,
        operations: list[dict],
        _context: dict | None = None,
        **_kwargs: Any,
    ) -> str:
        if not _context or not _context.get("user_id"):
            return json.dumps({"status": "error", "message": "No run context."})
        if not operations:
            return json.dumps({"status": "error", "message": "No operations provided."})

        service = FileService()
        try:
            content, asset = await service.download_asset(asset_id, _context["user_id"])
            new_bytes, notes = apply_edits(asset["file_type"], content, operations)
        except ValueError as exc:
            return json.dumps({"status": "error", "message": str(exc)})

        new_name = next_version_name(asset["file_name"])
        new_asset = await service.save_generated_file(
            user_id=_context["user_id"],
            conversation_id=_context["conversation_id"],
            run_id=_context["run_id"],
            filename=new_name,
            content=new_bytes,
            mime_type=asset["file_type"],
        )
        return json.dumps({
            "status": "success",
            "filename": new_name,
            "download_url": new_asset["file_url"],
            "asset_id": new_asset["id"],
            "file_type": new_asset["file_type"],
            "file_size": new_asset["file_size"],
            "edited_from": asset["file_name"],
            "edits": notes,
        })
