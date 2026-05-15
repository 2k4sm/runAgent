"""SSE event formatting."""

from datetime import UTC, datetime

from run_agent.schemas.sse import SSEEvent


class StreamService:
    """Format agent events as SSE `data:` payloads."""

    @staticmethod
    def format(event: SSEEvent) -> str:
        if event.timestamp is None:
            event.timestamp = datetime.now(UTC).isoformat()
        return f"data: {event.model_dump_json()}\n\n"
