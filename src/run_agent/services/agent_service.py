"""Agent orchestration — runs the supervisor pipeline and persists results."""

import base64
import io
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import httpx

from run_agent.agents.supervisor import SupervisorAgent
from run_agent.config import constants
from run_agent.config.logging import get_logger
from run_agent.schemas.sse import SSEEvent
from run_agent.services.run_service import RunService

logger = get_logger(__name__)


async def build_multimodal_content(
    content: str,
    attachments: list[dict[str, Any]],
) -> str | list[dict[str, Any]]:
    """Build LLM message content from text plus any attachments.

    Returns a plain string when there are no attachments, otherwise a
    multimodal content array.
    """
    if not attachments:
        return content

    parts: list[dict[str, Any]] = [{"type": "text", "text": content}]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attachment in attachments:
            file_type = attachment["file_type"]
            try:
                response = await client.get(attachment["file_url"])
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("attachment_fetch_failed", error=str(exc))
                continue

            if file_type.startswith("image/"):
                b64 = base64.b64encode(response.content).decode()
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{file_type};base64,{b64}"},
                })
            elif file_type == constants.MIME_PDF:
                text = _extract_pdf_text(response.content)
                parts.append({
                    "type": "text",
                    "text": f"\n\n[Attached PDF: {attachment['file_name']}]\n{text}",
                })
            else:
                # Treat anything else as UTF-8 text where possible.
                try:
                    text = response.content.decode("utf-8", errors="ignore")
                except (UnicodeDecodeError, AttributeError):
                    text = ""
                parts.append({
                    "type": "text",
                    "text": f"\n\n[Attached file: {attachment['file_name']}]\n{text[:8000]}",
                })

    return parts


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)[:8000]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _attachment_entry(asset: dict[str, Any]) -> dict[str, Any]:
    """Trim an asset dict to the fields the UI needs to render a chip."""
    return {
        "id": asset["id"],
        "file_name": asset["file_name"],
        "file_type": asset["file_type"],
        "file_size": asset.get("file_size", 0),
        "file_url": asset.get("file_url", ""),
    }


def _event_entry(event: SSEEvent) -> dict[str, Any]:
    """Convert an SSE event into an ordered timeline entry."""
    return {
        "kind": "event",
        "type": event.type,
        "agent": event.agent,
        "content": event.content,
        "metadata": event.metadata,
        "ts": event.timestamp or _now(),
    }


class AgentService:
    def __init__(self) -> None:
        self.run_service = RunService()

    async def execute(
        self,
        run_id: str,
        user_id: str,
        conversation_id: str,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the supervisor pipeline, streaming SSE events and persisting state.

        Every yielded event and the bracketing user/assistant messages are
        accumulated into an ordered `timeline`, persisted onto the run's `data`
        column once the run ends — on success, failure, or early client abort.
        """
        attachments = attachments or []
        # `usage` is filled in by each agent with exact provider-reported token
        # counts as the run progresses (see BaseAgent._accumulate_usage).
        context: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        # Read prior turns BEFORE persisting this run's timeline, otherwise the
        # current message would appear twice in the LLM context.
        history = await self.run_service.history(conversation_id)

        # The timeline opens with the user message entry.
        timeline: list[dict[str, Any]] = [{
            "kind": "message",
            "role": constants.ROLE_USER,
            "agent": None,
            "content": content,
            "attachments": [_attachment_entry(a) for a in attachments],
            "ts": _now(),
        }]

        message_content = await build_multimodal_content(content, attachments)
        messages = [*history, {"role": "user", "content": message_content}]

        assistant_chunks: list[str] = []
        final_agent = constants.AGENT_SUPERVISOR
        persisted = False

        try:
            supervisor = SupervisorAgent()
            async for event in supervisor.run(messages, context):
                if event.type == "chunk" and event.content:
                    # The loop now streams text token-by-token; keep the
                    # per-token deltas out of the persisted timeline (the
                    # assembled assistant message entry below captures the
                    # full text) and just forward them to the client.
                    assistant_chunks.append(event.content)
                    final_agent = event.agent
                    yield event
                    continue
                timeline.append(_event_entry(event))
                yield event

            answer = "".join(assistant_chunks)
            if answer:
                timeline.append({
                    "kind": "message",
                    "role": constants.ROLE_ASSISTANT,
                    "agent": final_agent,
                    "content": answer,
                    "ts": _now(),
                })
            usage = context["usage"]
            await self.run_service.complete_run(
                run_id,
                data=timeline,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )
            persisted = True

        except Exception as exc:  # noqa: BLE001
            logger.error("agent_execution_failed", run_id=run_id, error=str(exc))
            for event in (
                SSEEvent(
                    type="error",
                    agent=final_agent,
                    content="The agent encountered an error and could not complete.",
                ),
                SSEEvent(type="done", agent=final_agent),
            ):
                event.timestamp = _now()
                timeline.append(_event_entry(event))
                yield event
            await self.run_service.fail_run(run_id, str(exc), data=timeline)
            persisted = True

        finally:
            # The generator was closed early (client abort) before either
            # terminal branch ran — persist whatever streamed so the run is
            # never left stuck in `running` with an empty timeline.
            if not persisted:
                timeline.append(_event_entry(
                    SSEEvent(type="status", agent=final_agent,
                             content="aborted", timestamp=_now()),
                ))
                timeline.append(_event_entry(
                    SSEEvent(type="done", agent=final_agent, timestamp=_now()),
                ))
                # Never let a persistence failure mask the GeneratorExit that
                # brought us here — that would surface as a RuntimeError.
                try:
                    await self.run_service.fail_run(run_id, "aborted", data=timeline)
                except Exception as exc:  # noqa: BLE001
                    logger.error("abort_persist_failed", run_id=run_id, error=str(exc))
