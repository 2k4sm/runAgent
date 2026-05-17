"""List the files available in the current conversation."""

import json
from typing import Any

from run_agent.services.file_service import FileService
from run_agent.tools.base import BaseTool


class ListDocumentsTool(BaseTool):
    name = "list_documents"
    description = (
        "List every file in this conversation — both user uploads and previously "
        "generated documents. Call this first when the user asks to edit, update, "
        "or refer to an existing document, to find its asset_id."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, _context: dict | None = None, **_kwargs: Any) -> str:
        if not _context or not _context.get("conversation_id"):
            return json.dumps({"status": "error", "message": "No conversation context."})

        files = await FileService().list_conversation_files(
            _context["conversation_id"], _context["user_id"]
        )
        return json.dumps({
            "status": "success",
            "documents": [
                {
                    "asset_id": f["id"],
                    "file_name": f["file_name"],
                    "file_type": f["file_type"],
                    "file_size": f["file_size"],
                    "source": f["source"],
                    "created_at": str(f.get("created_at", "")),
                }
                for f in files
            ],
        })
