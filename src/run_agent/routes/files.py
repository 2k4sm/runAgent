"""File / asset routes.

Files are uploaded here, ahead of (and separately from) sending a chat
message. The chat endpoint then references the resulting asset by id. These
routes also expose asset metadata plus a public download URL, and deletion.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile

from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser
from run_agent.schemas.file import AssetOut
from run_agent.services.conversation_service import ConversationService
from run_agent.services.file_service import FileService

router = APIRouter()


@router.post("/upload", response_model=AssetOut)
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Store a file and return its asset record (with id and download URL).

    `conversation_id` is optional: a brand-new chat has no conversation yet,
    so the asset is stored unattached and linked via the run timeline on send.
    """
    if conversation_id:
        # Ownership check — raises if the conversation is not the caller's.
        await ConversationService().get(conversation_id, user.id)
    content = await file.read()
    return await FileService().upload_attachment(
        user_id=user.id,
        conversation_id=conversation_id,
        file_name=file.filename or "unnamed",
        content=content,
        mime_type=file.content_type or "application/octet-stream",
    )


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    return await FileService().get_asset(asset_id, user.id)


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    await FileService().delete_asset(asset_id, user.id)
    return {"status": "deleted"}
