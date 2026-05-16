"""LiteLLM completion wrappers.

The ReAct loop drives a single *streaming* call (`stream_llm`) per iteration:
text deltas are emitted to the client as they arrive, and the caller rebuilds
the full response — including `tool_calls` and `usage` — from the accumulated
chunks via `litellm.stream_chunk_builder`. Rebuilding makes tool-call detection
reliable even on providers where raw streamed tool-call deltas are flaky.
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

import litellm
from litellm import acompletion

from run_agent.config.settings import settings

# LiteLLM reads provider keys from the environment based on the model prefix.
os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)

# Drop params a given provider does not support rather than erroring.
litellm.drop_params = True


async def stream_llm(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: Any = "auto",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
) -> AsyncGenerator[Any, None]:
    """Streaming LLM call used by the ReAct loop.

    Yields raw LiteLLM chunks. The caller accumulates them and uses
    `litellm.stream_chunk_builder(chunks, messages=...)` to rebuild the full
    response (`tool_calls` + provider-reported `usage`).
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if reasoning_effort:
        # Standardized by LiteLLM; dropped automatically for providers that
        # do not support it (litellm.drop_params is enabled above).
        kwargs["reasoning_effort"] = reasoning_effort

    response = await acompletion(**kwargs)

    async for chunk in response:
        yield chunk
