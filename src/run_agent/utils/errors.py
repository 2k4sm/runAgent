"""Maps raw agent/LLM exceptions to clear, user-facing messages.

The ReAct loop surfaces provider errors (LiteLLM, MCP, network) as opaque
stack-trace strings. `friendly_error_message` classifies the failure — by
exception type and by signals in the message — and returns a short sentence the
UI can show directly. The raw error is still logged and stored for debugging.
"""

import re

_RETRY_PATTERNS = (
    re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE),
    re.compile(r'"retryDelay":\s*"(\d+)s"'),
    re.compile(r"retry[_-]?delay[\"']?[:\s]+([\d.]+)", re.IGNORECASE),
)


def _retry_hint(text: str) -> str:
    """Return a ' Please try again in ~Ns.' suffix if the error names a delay."""
    for pattern in _RETRY_PATTERNS:
        match = pattern.search(text)
        if match:
            seconds = round(float(match.group(1)))
            return f" Please try again in about {max(seconds, 1)} seconds."
    return ""


def friendly_error_message(exc: Exception) -> str:
    """Return a concise, user-facing explanation for an agent failure."""
    raw = str(exc)
    text = raw.lower()

    # Rate limits / quota exhaustion (429 / RESOURCE_EXHAUSTED).
    if (
        "ratelimiterror" in text
        or "resource_exhausted" in text
        or "exceeded your current quota" in text
        or "quota exceeded" in text
        or "too many requests" in text
        or "error code: 429" in text
        or "code\": 429" in text
    ):
        return (
            "The AI service is busy right now — it has hit its rate limit or "
            "usage quota." + (_retry_hint(raw) or " Please try again shortly.")
        )

    # Authentication / authorization with the AI provider.
    if (
        "authenticationerror" in text
        or "invalid api key" in text
        or "permissiondeniederror" in text
        or "error code: 401" in text
        or "error code: 403" in text
    ):
        return (
            "The AI service rejected the request because of an authentication "
            "problem. Please contact support."
        )

    # Conversation too long for the model.
    if (
        "contextwindowexceeded" in text
        or "context window" in text
        or "maximum context length" in text
        or "context length exceeded" in text
    ):
        return (
            "This conversation has grown too long for the model. Start a new "
            "conversation or shorten your request, then try again."
        )

    # Provider overloaded / unavailable (5xx).
    if (
        "serviceunavailable" in text
        or "internalservererror" in text
        or "overloaded" in text
        or "error code: 503" in text
        or "error code: 529" in text
        or "error code: 500" in text
    ):
        return (
            "The AI service is temporarily overloaded."
            + (_retry_hint(raw) or " Please try again shortly.")
        )

    # Timeouts and network failures.
    if (
        "timeout" in text
        or "timed out" in text
        or "apiconnectionerror" in text
        or "connection error" in text
    ):
        return (
            "The AI service took too long to respond or could not be reached. "
            "Please try again."
        )

    # Content blocked by the provider's safety policy.
    if "contentpolicyviolation" in text or "content policy" in text:
        return "The request was blocked by the AI provider's content policy."

    return "The agent encountered an unexpected error and could not complete. Please try again."
