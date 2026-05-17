"""Shared helpers for document creation tools."""

import json
import re
from typing import Any

from run_agent.services.file_service import FileService

_VERSION_RE = re.compile(r"^(.*)-v(\d+)$")


async def finalize(
    filename: str,
    content: bytes,
    mime_type: str,
    context: dict[str, Any] | None,
) -> str:
    """Upload a generated file and return a JSON result string for the LLM.

    When run context is absent (e.g. unit tests), returns success without
    persisting — the document bytes were still produced correctly.
    """
    if not context:
        return json.dumps({
            "status": "success",
            "filename": filename,
            "note": "created but not persisted (no run context)",
        })

    asset = await FileService().save_generated_file(
        user_id=context["user_id"],
        conversation_id=context["conversation_id"],
        run_id=context["run_id"],
        filename=filename,
        content=content,
        mime_type=mime_type,
    )
    return json.dumps({
        "status": "success",
        "filename": filename,
        "download_url": asset["file_url"],
        "asset_id": asset["id"],
        "file_type": asset["file_type"],
        "file_size": asset["file_size"],
    })


def filename_with_ext(filename: str, ext: str) -> str:
    """Ensure `filename` ends with `.ext`."""
    suffix = f".{ext}"
    return filename if filename.lower().endswith(suffix) else f"{filename}{suffix}"


def next_version_name(file_name: str) -> str:
    """Return the next versioned name: `report.docx` -> `report-v2.docx`,
    `report-v2.docx` -> `report-v3.docx`."""
    dot = file_name.rfind(".")
    stem, ext = (file_name[:dot], file_name[dot:]) if dot > 0 else (file_name, "")
    match = _VERSION_RE.match(stem)
    if match:
        return f"{match.group(1)}-v{int(match.group(2)) + 1}{ext}"
    return f"{stem}-v2{ext}"
