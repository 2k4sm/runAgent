"""runs table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class RunRepository(BaseRepository):
    table_name = "runs"

    async def get_by_id_and_user(
        self, run_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Return the run only if it belongs to the given user."""
        response = (
            self.table.select("*")
            .eq("id", run_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    async def list_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return every run for a conversation, oldest first, with its timeline."""
        response = (
            self.table.select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data
