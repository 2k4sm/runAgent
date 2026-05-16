"""runs table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class RunRepository(BaseRepository):
    table_name = "runs"

    async def list_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return every run for a conversation, oldest first, with its timeline."""
        response = (
            self.table.select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data
