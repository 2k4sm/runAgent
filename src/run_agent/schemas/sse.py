"""SSE event envelope."""

from typing import Any, Literal

from pydantic import BaseModel

SSEEventType = Literal[
    "chunk",
    "reasoning",
    "agent_response",
    "tool_call",
    "tool_result",
    "handoff",
    "status",
    "error",
    "done",
]


class SSEEvent(BaseModel):
    """A single server-sent event in the chat stream."""

    type: SSEEventType
    agent: str
    content: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str | None = None
