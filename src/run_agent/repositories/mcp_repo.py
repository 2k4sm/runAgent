"""mcp_servers table queries."""

from typing import Any

from run_agent.repositories.base import BaseRepository


class MCPServerRepository(BaseRepository):
    table_name = "mcp_servers"

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return a user's MCP servers, oldest first."""
        response = (
            self.table.select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []

    async def get_for_user(
        self, server_id: str, user_id: str
    ) -> dict[str, Any] | None:
        response = (
            self.table.select("*")
            .eq("id", server_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
