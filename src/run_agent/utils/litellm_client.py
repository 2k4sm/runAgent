"""LiteLLM completion wrappers.

The ReAct loop uses the *non-streaming* `call_llm` for tool-call detection
(streaming tool calls are unreliable on some Gemini models) and `stream_llm`
only for final text responses.
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


async def call_llm(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: Any = "auto",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Any:
    """Non-streaming LLM call (used for tool-use detection in the ReAct loop).

    Returns the full LiteLLM response so callers can read both
    `response.choices[0].message` and `response.usage` (exact provider-reported
    token counts).
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    return await acompletion(**kwargs)


async def stream_llm(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """Streaming LLM call (used for final text responses)."""
    response = await acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
