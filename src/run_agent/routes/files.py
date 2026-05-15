"""File / asset routes.

Uploads happen through the chat endpoint (multipart attachments) or directly
to Supabase Storage from the client. These routes expose asset metadata and a
signed download URL, and allow deletion.
"""

from fastapi import APIRouter, Depends

from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser
from run_agent.schemas.file import AssetOut
from run_agent.services.file_service import FileService

router = APIRouter()


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
