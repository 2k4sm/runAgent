"""Per-user in-memory token-bucket rate limiting.

In-memory only — for multi-instance deployments move this to Redis.
"""

import time

from fastapi import Depends, HTTPException

from run_agent.config.settings import settings
from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser


class _TokenBucket:
    def __init__(self, rate_per_minute: int) -> None:
        self.capacity = float(rate_per_minute)
        self.refill_per_sec = rate_per_minute / 60.0
        self.tokens = float(rate_per_minute)
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(
            self.capacity,
            self.tokens + (now - self.updated) * self.refill_per_sec,
        )
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_buckets: dict[str, _TokenBucket] = {}


async def rate_limit(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that enforces a per-user request rate limit."""
    bucket = _buckets.get(user.id)
    if bucket is None:
        bucket = _TokenBucket(settings.rate_limit_requests_per_minute)
        _buckets[user.id] = bucket

    if not bucket.allow():
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return user
