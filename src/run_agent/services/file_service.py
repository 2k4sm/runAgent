"""File service — Supabase Storage uploads/deletes plus asset records.

This is the storage isolation boundary: agents and tools call here, never the
storage client directly. Asset rows store only the object `storage_path`;
`file_url` is the public URL added to returned dicts on demand.
"""

from typing import Any

from run_agent.config import constants
from run_agent.repositories.asset_repo import AssetRepository
from run_agent.utils import storage_client
from run_agent.utils.id_gen import new_id


def _build_path(user_id: str, conversation_id: str | None, file_name: str) -> str:
    """Object path: <user_id>/<conversation_id>/<uuid>_<file_name>.

    Files uploaded before a conversation exists land under `unassigned`.
    """
    return f"{user_id}/{conversation_id or 'unassigned'}/{new_id()}_{file_name}"


def _with_url(asset: dict[str, Any]) -> dict[str, Any]:
    """Return the asset dict with a public `file_url` added."""
    return {**asset, "file_url": storage_client.public_url(asset["storage_path"])}


class FileService:
    def __init__(self) -> None:
        self.asset_repo = AssetRepository()

    async def _create(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        run_id: str | None,
        source: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        path = _build_path(user_id, conversation_id, file_name)
        storage_client.upload(path, content, mime_type)
        asset = await self.asset_repo.create({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "source": source,
            "file_name": file_name,
            "file_type": mime_type,
            "file_size": len(content),
            "storage_path": path,
        })
        return _with_url(asset)

    async def upload_attachment(
        self,
        user_id: str,
        file_name: str,
        content: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        """Upload a user attachment and create an asset record."""
        return await self._create(
            user_id=user_id,
            conversation_id=None,
            run_id=None,
            source=constants.SOURCE_UPLOAD,
            file_name=file_name,
            content=content,
            mime_type=mime_type,
        )

    async def save_generated_file(
        self,
        user_id: str,
        conversation_id: str,
        run_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        """Upload an agent-generated file and create an asset record."""
        return await self._create(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            source=constants.SOURCE_GENERATED,
            file_name=filename,
            content=content,
            mime_type=mime_type,
        )

    async def get_asset(self, asset_id: str, user_id: str) -> dict[str, Any]:
        asset = await self.asset_repo.get_by_id_and_user(asset_id, user_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        return _with_url(asset)

    async def download_asset(
        self, asset_id: str, user_id: str
    ) -> tuple[bytes, dict[str, Any]]:
        """Return an asset's raw bytes alongside its record (with `file_url`)."""
        asset = await self.get_asset(asset_id, user_id)
        content = storage_client.download(asset["storage_path"])
        return content, asset

    async def list_conversation_files(
        self, conversation_id: str, user_id: str
    ) -> list[dict[str, Any]]:
        """Return every asset in a conversation, each with a public `file_url`."""
        rows = await self.asset_repo.list_by_conversation(conversation_id, user_id)
        return [_with_url(r) for r in rows]

    async def delete_asset(self, asset_id: str, user_id: str) -> None:
        asset = await self.asset_repo.get_by_id_and_user(asset_id, user_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        storage_client.remove(asset["storage_path"])
        await self.asset_repo.delete(asset_id)
