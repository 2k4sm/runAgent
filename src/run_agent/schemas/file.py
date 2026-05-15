"""File / asset models."""

from datetime import datetime

from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    user_id: str
    conversation_id: str | None = None
    run_id: str | None = None
    source: str
    file_name: str
    file_type: str
    file_size: int
    storage_path: str
    file_url: str  # public download URL (not persisted)
    created_at: datetime
