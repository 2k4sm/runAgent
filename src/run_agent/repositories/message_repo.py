"""messages table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class MessageRepository(BaseRepository):
    table_name = "messages"

    async def list_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        response = (
            self.table.select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data
