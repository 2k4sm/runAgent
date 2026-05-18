"""Conversation request/response models."""

from datetime import datetime

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    # Optional client-supplied id, enabling optimistic creation on the client.
    id: str | None = None


class ConversationOut(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
