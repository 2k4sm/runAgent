"""assets table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class AssetRepository(BaseRepository):
    table_name = "assets"

    async def get_by_id_and_user(self, asset_id: str, user_id: str) -> dict[str, Any] | None:
        response = (
            self.table.select("*")
            .eq("id", asset_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
