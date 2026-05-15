"""conversations table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    table_name = "conversations"

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        response = (
            self.table.select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data

    async def get_for_user(self, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        response = (
            self.table.select("*")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
