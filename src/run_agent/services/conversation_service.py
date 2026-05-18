"""Conversation create/list/delete operations."""

from typing import Any

from run_agent.repositories.conversation_repo import ConversationRepository


class ConversationService:
    def __init__(self) -> None:
        self.repo = ConversationRepository()

    async def create(
        self,
        user_id: str,
        title: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"user_id": user_id, "title": title}
        # A client-supplied id enables optimistic creation; absent → DB default.
        if conversation_id:
            data["id"] = conversation_id
        return await self.repo.create(data)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return await self.repo.list_for_user(user_id)

    async def get(self, conversation_id: str, user_id: str) -> dict[str, Any]:
        conversation = await self.repo.get_for_user(conversation_id, user_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        return conversation

    async def delete(self, conversation_id: str, user_id: str) -> None:
        await self.get(conversation_id, user_id)  # ownership check
        await self.repo.delete(conversation_id)
