"""BaseAgent — the shared ReAct loop.

Each agent runs Thought -> Action -> Observation until it produces a final
answer. Every iteration drives a single *streaming* LLM call: text deltas are
emitted to the client as they arrive, and the full response — including
`tool_calls` and `usage` — is rebuilt from the accumulated chunks via
`litellm.stream_chunk_builder`, so tool-call detection stays reliable.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import litellm

from run_agent.config.logging import get_logger
from run_agent.config.settings import settings
from run_agent.schemas.sse import SSEEvent
from run_agent.tools.registry import ToolRegistry
from run_agent.utils.litellm_client import stream_llm

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Base class implementing the ReAct loop pattern."""

    def __init__(
        self,
        name: str,
        tool_registry: ToolRegistry | None = None,
        model: str | None = None,
    ) -> None:
        self.name = name
        self.tool_registry = tool_registry
        self.model = model or settings.default_model
        self.max_iterations = settings.max_react_iterations

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        ...

    def get_tools(self) -> list[dict[str, Any]]:
        """Return OpenAI-format tool schemas available to this agent."""
        return self.tool_registry.get_schemas() if self.tool_registry else []

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Execute a tool with bounded retries; never raises."""
        if not self.tool_registry:
            return f"Error: agent '{self.name}' has no tools"

        kwargs = dict(tool_args)
        if context:
            kwargs["_context"] = context

        last_error = ""
        for attempt in range(settings.max_tool_retries + 1):
            try:
                return await self.tool_registry.execute(tool_name, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning(
                    "tool_failed",
                    tool=tool_name,
                    attempt=attempt,
                    error=last_error,
                )
        return f"Error executing tool '{tool_name}': {last_error}"

    async def run(
        self,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Execute the ReAct loop, yielding SSE events."""
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": self.get_system_prompt()},
            *messages,
        ]
        tools = self.get_tools()
        reasoning_effort = (context or {}).get("reasoning_effort")

        for _ in range(self.max_iterations):
            # Stream the call: emit text deltas live, accumulate raw chunks so
            # the full response (tool_calls + usage) can be rebuilt afterward.
            chunks: list[Any] = []
            async for chunk in stream_llm(
                model=self.model,
                messages=conversation,
                tools=tools or None,
                reasoning_effort=reasoning_effort,
            ):
                chunks.append(chunk)
                if not chunk.choices:  # usage-only final chunk
                    continue
                delta = chunk.choices[0].delta
                if not delta:
                    continue
                # Reasoning tokens stream alongside content; LiteLLM
                # standardizes them on `delta.reasoning_content`.
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield SSEEvent(
                        type="reasoning", agent=self.name, content=reasoning
                    )
                if delta.content:
                    yield SSEEvent(
                        type="chunk", agent=self.name, content=delta.content
                    )

            response: Any = litellm.stream_chunk_builder(
                chunks, messages=conversation
            )
            if response is None:
                raise RuntimeError("LLM stream produced no chunks")
            _accumulate_usage(context, response)
            message = response.choices[0].message

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                # Final answer — text was already streamed above.
                yield SSEEvent(
                    type="done",
                    agent=self.name,
                    metadata={"usage": _usage_snapshot(context)},
                )
                return

            # Record the assistant turn (with its tool calls) once.
            conversation.append(_message_to_dict(message))

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                raw_args = tool_call.function.arguments
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})

                # `_handle_tool` yields the events for this call; the content of
                # its final `tool_result` event is what the model sees as the
                # tool's output. Subclasses (e.g. the supervisor) override it to
                # run sub-agents and stream their events through here.
                result = ""
                async for event in self._handle_tool(
                    tool_name, args, tool_call.id, context
                ):
                    if event.type == "tool_result":
                        result = event.content or ""
                    yield event

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        yield SSEEvent(
            type="error",
            agent=self.name,
            content=f"Agent exceeded max iterations ({self.max_iterations})",
        )

    async def _handle_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_call_id: str,
        context: dict[str, Any] | None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Handle one tool call, yielding its events.

        The default runs a registered tool. The final `tool_result` event's
        `content` becomes the tool message appended to the conversation, so an
        override MUST yield exactly one `tool_result` event.
        """
        yield SSEEvent(
            type="thought",
            agent=self.name,
            content=f"Using tool: {tool_name}",
        )
        metadata: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_args": args,
            "tool_call_id": tool_call_id,
        }
        # MCP tools carry their server's favicon; surface it so the UI can
        # show the real service icon for this tool call.
        tool = self.tool_registry.get(tool_name) if self.tool_registry else None
        icon_url = getattr(tool, "icon_url", None)
        if icon_url:
            metadata["tool_icon"] = icon_url
        yield SSEEvent(type="tool_call", agent=self.name, metadata=metadata)
        result = await self.execute_tool(tool_name, args, context)
        yield SSEEvent(
            type="tool_result",
            agent=self.name,
            content=result,
            metadata={"tool_name": tool_name},
        )


def _accumulate_usage(context: dict[str, Any] | None, response: Any) -> None:
    """Add this response's provider-reported token usage to the shared context.

    The same `context` dict is threaded through the supervisor and every worker
    agent, so it ends up holding the exact total for the whole run.
    """
    if context is None:
        return
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    bucket = context.setdefault(
        "usage",
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )
    bucket["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    bucket["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
    bucket["total_tokens"] += getattr(usage, "total_tokens", 0) or 0


def _usage_snapshot(context: dict[str, Any] | None) -> dict[str, int]:
    """Return a copy of the cumulative usage so far (zeros if none)."""
    default = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if context is None:
        return default
    return dict(context.get("usage", default))


def _message_to_dict(message: Any) -> dict[str, Any]:
    """Normalize a LiteLLM message object to a plain chat-message dict."""
    if hasattr(message, "model_dump"):
        data = message.model_dump()
    elif isinstance(message, dict):
        data = dict(message)
    else:
        data = {"role": "assistant", "content": str(message)}
    # Keep only the keys the chat API expects.
    return {
        k: v
        for k, v in data.items()
        if k in ("role", "content", "tool_calls", "tool_call_id", "name") and v is not None
    }
