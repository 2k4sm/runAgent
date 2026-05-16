"""Run lifecycle and timeline persistence.

A run owns its entire conversation turn: the `data` column holds one
chronologically ordered array of message and event entries (see
`agent_service` for the entry shapes). There is no separate messages table.
"""

from datetime import UTC, datetime
from typing import Any

from run_agent.config import constants
from run_agent.repositories.run_repo import RunRepository


class RunService:
    def __init__(self) -> None:
        self.run_repo = RunRepository()

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
        data: list[dict[str, Any]],
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        await self.run_repo.update(run_id, {
            "status": constants.RUN_COMPLETED,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "data": data,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    async def fail_run(
        self,
        run_id: str,
        error: str,
        data: list[dict[str, Any]],
    ) -> None:
        await self.run_repo.update(run_id, {
            "status": constants.RUN_FAILED,
            "error": error,
            "data": data,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    async def history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return prior turns as LLM chat messages, drawn from completed runs.

        Only completed runs contribute, so a failed/partial run never pollutes
        the context. The current run exists but its `data` is still empty.
        """
        runs = await self.run_repo.list_for_conversation(conversation_id)
        messages: list[dict[str, Any]] = []
        for run in runs:
            if run["status"] != constants.RUN_COMPLETED:
                continue
            for entry in run.get("data") or []:
                if entry.get("kind") != "message":
                    continue
                if entry.get("role") in (constants.ROLE_USER, constants.ROLE_ASSISTANT):
                    messages.append({
                        "role": entry["role"],
                        "content": entry.get("content") or "",
                    })
        return messages
