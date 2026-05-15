"""Agent / tool event models."""

from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


class RunContext(BaseModel):
    """Context threaded through agent execution and into tools."""

    run_id: str
    user_id: str
    conversation_id: str
