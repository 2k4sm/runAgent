"""ID generation helpers."""

import uuid


def new_id() -> str:
    """Return a new UUID4 string."""
    return str(uuid.uuid4())
