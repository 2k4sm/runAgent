"""Auth request/response models."""

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """The authenticated user resolved from a Supabase JWT."""

    id: str
    email: str | None = None
    role: str | None = None
