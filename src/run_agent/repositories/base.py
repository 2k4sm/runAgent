"""Base repository — wraps the Supabase client.

Supabase's Python client is synchronous. Repository methods are declared
`async` for a uniform call site, but execute synchronously; queries are short
table reads/writes so this is acceptable for SME scale.
"""

from typing import Any

from supabase import Client

from run_agent.utils.supabase_client import get_supabase


class BaseRepository:
    """Common Supabase access for table repositories."""

    table_name: str

    def __init__(self) -> None:
        self.client: Client = get_supabase()

    @property
    def table(self) -> Any:
        return self.client.table(self.table_name)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        response = self.table.insert(data).execute()
        return response.data[0]

    async def get(self, row_id: str) -> dict[str, Any] | None:
        response = self.table.select("*").eq("id", row_id).limit(1).execute()
        return response.data[0] if response.data else None

    async def update(self, row_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        response = self.table.update(data).eq("id", row_id).execute()
        return response.data[0] if response.data else None

    async def delete(self, row_id: str) -> None:
        self.table.delete().eq("id", row_id).execute()
