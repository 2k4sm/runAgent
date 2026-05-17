"""Supabase Storage helpers.

The only module that talks to Supabase Storage. `FileService` is the consumer;
agents, tools, and routes never touch storage directly.

The `assets` bucket is public — downloads use permanent public URLs.
"""

from typing import Any

from run_agent.config.settings import settings
from run_agent.utils.supabase_client import get_supabase


def _bucket() -> Any:
    return get_supabase().storage.from_(settings.supabase_storage_bucket)


def upload(path: str, content: bytes, mime_type: str) -> None:
    """Upload bytes to `path` in the assets bucket (overwriting if present)."""
    _bucket().upload(
        path=path,
        file=content,
        file_options={"content-type": mime_type, "upsert": "true"},
    )


def download(path: str) -> bytes:
    """Download an object's raw bytes from the assets bucket."""
    return bytes(_bucket().download(path))


def public_url(path: str) -> str:
    """Return the public download URL for an object."""
    return str(_bucket().get_public_url(path))


def remove(path: str) -> None:
    """Delete an object from the assets bucket."""
    _bucket().remove([path])
