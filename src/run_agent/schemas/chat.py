"""Chat request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChatMessageIn(BaseModel):
    """Body of POST /chat/message — references already-uploaded attachments."""

    content: str
    conversation_id: str
    attachment_ids: list[str] = []
    reasoning: bool = False


class RunOut(BaseModel):
    """A run with its full ordered message+event timeline in `data`."""

    id: str
    conversation_id: str
    status: str
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    data: list[dict[str, Any]] = []
    created_at: datetime
    completed_at: datetime | None = None
