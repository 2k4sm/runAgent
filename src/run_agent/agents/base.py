"""BaseAgent — the shared ReAct loop.

Each agent runs Thought -> Action -> Observation until it produces a final
answer. Every iteration drives a single *streaming* LLM call: text deltas are
emitted to the client as they arrive, and the full response — including
`tool_calls` and `usage` — is rebuilt from the accumulated chunks via
`litellm.stream_chunk_builder`, so tool-call detection stays reliable.
"""

import asyncio
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

# Queue marker signalling one concurrent tool call has finished streaming.
_TOOL_DONE = object()


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

    def _compose_system_prompt(self, context: dict[str, Any] | None) -> str:
        """Return the system prompt with shared run context appended.

        Currently this folds in the user's current date/time (set once per run
        in AgentService) so every agent reasons about 'now' consistently.
        """
        prompt = self.get_system_prompt()
        time_context = (context or {}).get("time_context")
        if time_context:
            prompt = f"{prompt}\n\n{time_context}"
        return prompt

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
            {"role": "system", "content": self._compose_system_prompt(context)},
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
                # standardizes them on `delta.reasoning_content`. Only surface
                # them when the user enabled reasoning — some models (e.g.
                # Gemma) emit reasoning regardless of what we request.
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning and reasoning_effort:
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

            # Run every tool call this turn requested concurrently — when the
            # model emits multiple independent calls they finish in parallel
            # instead of one-by-one. Each `_handle_tool` generator drains into a
            # shared queue so their events merge in arrival order; the tool
            # messages are still appended in the model's original order.
            results: dict[str, str] = {}
            errors: list[BaseException] = []
            queue: asyncio.Queue[Any] = asyncio.Queue()
            tasks = [
                asyncio.create_task(
                    self._drain_tool_call(tc, queue, results, errors, context)
                )
                for tc in tool_calls
            ]
            try:
                finished = 0
                while finished < len(tasks):
                    item = await queue.get()
                    if item is _TOOL_DONE:
                        finished += 1
                    else:
                        yield item
            finally:
                # On early close (client abort) cancel any still-running calls.
                for task in tasks:
                    if not task.done():
                        task.cancel()

            # A failure in any tool call ends the run (mirrors sequential behavior).
            if errors:
                raise errors[0]

            for tool_call in tool_calls:
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": results.get(tool_call.id, ""),
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
        # MCP tools carry their server's favicon; surface it for the UI.
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
            metadata={"tool_name": tool_name, "tool_call_id": tool_call_id},
        )

    async def _drain_tool_call(
        self,
        tool_call: Any,
        queue: "asyncio.Queue[Any]",
        results: dict[str, str],
        errors: list[BaseException],
        context: dict[str, Any] | None,
    ) -> None:
        """Run one tool call, pushing its events onto the shared queue.

        Records the `tool_result` content in `results` (keyed by call id) and
        any failure in `errors`; always ends with the `_TOOL_DONE` marker so
        the merging loop in `run()` knows this call is finished.
        """
        try:
            raw_args = tool_call.function.arguments
            args = (
                json.loads(raw_args)
                if isinstance(raw_args, str)
                else (raw_args or {})
            )
            async for event in self._handle_tool(
                tool_call.function.name, args, tool_call.id, context
            ):
                if event.type == "tool_result":
                    results[tool_call.id] = event.content or ""
                await queue.put(event)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            await queue.put(_TOOL_DONE)


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
