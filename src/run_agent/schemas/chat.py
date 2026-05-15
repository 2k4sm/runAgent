"""Chat request/response models."""

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    run_id: str | None = None
    role: str
    agent: str | None = None
    content: str | None = None
    metadata: dict = {}
