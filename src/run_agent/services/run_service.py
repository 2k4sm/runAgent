"""Run lifecycle and message persistence."""

from datetime import UTC, datetime
from typing import Any

from run_agent.config import constants
from run_agent.repositories.message_repo import MessageRepository
from run_agent.repositories.run_repo import RunRepository


class RunService:
    def __init__(self) -> None:
        self.run_repo = RunRepository()
        self.message_repo = MessageRepository()

    async def create_run(
        self,
        user_id: str,
        conversation_id: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        return await self.run_repo.create({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "status": constants.RUN_RUNNING,
            "model": model,
        })

    async def complete_run(
        self,
        run_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        await self.run_repo.update(run_id, {
            "status": constants.RUN_COMPLETED,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    async def fail_run(self, run_id: str, error: str) -> None:
        await self.run_repo.update(run_id, {
            "status": constants.RUN_FAILED,
            "error": error,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    async def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str | None,
        run_id: str | None = None,
        agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.message_repo.create({
            "conversation_id": conversation_id,
            "user_id": user_id,
            "run_id": run_id,
            "role": role,
            "agent": agent,
            "content": content,
            "metadata": metadata or {},
        })

    async def history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return prior messages formatted as LLM chat messages."""
        rows = await self.message_repo.list_for_conversation(conversation_id)
        return [
            {"role": row["role"], "content": row["content"] or ""}
            for row in rows
            if row["role"] in (constants.ROLE_USER, constants.ROLE_ASSISTANT)
        ]
