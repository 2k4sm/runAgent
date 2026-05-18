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
from run_agent.services.mcp_service import MCPServerService
from run_agent.services.run_service import RunService
from run_agent.utils.errors import friendly_error_message

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
        reasoning: bool = False,
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
        # When enabled, every agent passes this effort to the LLM call and
        # streams the model's reasoning tokens back as `reasoning` events.
        if reasoning:
            context["reasoning_effort"] = "medium"

        # Offer the user's connected MCP servers to the supervisor so it can
        # delegate to the dynamic MCP agent. Absent → the feature is invisible.
        try:
            mcp_rows = await MCPServerService().list_active_rows(user_id)
            if mcp_rows:
                context["mcp_servers"] = [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "description": row.get("description"),
                        "tools": row.get("tools_cache") or [],
                    }
                    for row in mcp_rows
                ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_catalog_load_failed", error=str(exc))

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

        final_agent = constants.AGENT_SUPERVISOR
        persisted = False

        # Text and reasoning stream token-by-token; the per-token deltas are
        # kept out of the persisted timeline. Instead, each agent's contiguous
        # run of text is merged into one `message` entry (and reasoning into one
        # `reasoning` entry) and flushed into the timeline in order — so a
        # multi-agent run (research -> document -> supervisor) replays as a
        # faithful sequence of per-agent messages.
        buf_agent: str | None = None
        buf_chunks: list[str] = []
        buf_reasoning: list[str] = []

        def flush_text() -> None:
            nonlocal buf_agent, buf_chunks, buf_reasoning
            if buf_agent is not None:
                reasoning = "".join(buf_reasoning)
                if reasoning:
                    timeline.append(_event_entry(SSEEvent(
                        type="reasoning", agent=buf_agent,
                        content=reasoning, timestamp=_now(),
                    )))
                answer = "".join(buf_chunks)
                if answer:
                    # Only the supervisor's text is the final assistant message;
                    # worker text is persisted as a collapsible `agent_response`.
                    if buf_agent == constants.AGENT_SUPERVISOR:
                        timeline.append({
                            "kind": "message",
                            "role": constants.ROLE_ASSISTANT,
                            "agent": buf_agent,
                            "content": answer,
                            "ts": _now(),
                        })
                    else:
                        timeline.append(_event_entry(SSEEvent(
                            type="agent_response", agent=buf_agent,
                            content=answer, timestamp=_now(),
                        )))
            buf_agent, buf_chunks, buf_reasoning = None, [], []

        try:
            supervisor = SupervisorAgent()
            async for event in supervisor.run(messages, context):
                if event.type in ("chunk", "reasoning") and event.content:
                    if buf_agent is not None and event.agent != buf_agent:
                        flush_text()
                    buf_agent = event.agent
                    final_agent = event.agent
                    if event.type == "chunk":
                        buf_chunks.append(event.content)
                    else:
                        buf_reasoning.append(event.content)
                    yield event
                    continue
                # A non-text event: flush buffered text first so the merged
                # message keeps its place in the ordered timeline.
                flush_text()
                timeline.append(_event_entry(event))
                yield event

            flush_text()
            # Attach any agent-generated files to the final assistant message
            # so the client renders them as download chips on that message.
            generated = context.get("generated_files")
            if generated:
                for entry in reversed(timeline):
                    if (
                        entry.get("kind") == "message"
                        and entry.get("role") == constants.ROLE_ASSISTANT
                    ):
                        entry["files"] = generated
                        break
            usage = context["usage"]
            await self.run_service.complete_run(
                run_id,
                data=timeline,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )
            persisted = True
            await self._log_usage(run_id, conversation_id, usage)

        except Exception as exc:  # noqa: BLE001
            logger.error("agent_execution_failed", run_id=run_id, error=str(exc))
            flush_text()  # persist any text streamed before the failure
            # Surface a clear, cause-specific message to the user; the raw
            # error is still logged above and stored on the run for debugging.
            for event in (
                SSEEvent(
                    type="error",
                    agent=final_agent,
                    content=friendly_error_message(exc),
                    metadata={"run_id": run_id},
                ),
                SSEEvent(type="done", agent=final_agent),
            ):
                event.timestamp = _now()
                timeline.append(_event_entry(event))
                yield event
            await self.run_service.fail_run(run_id, str(exc), data=timeline)
            persisted = True
            await self._log_usage(run_id, conversation_id, context["usage"])

        finally:
            # The generator was closed early (client abort) before either
            # terminal branch ran — persist whatever streamed so the run is
            # never left stuck in `running` with an empty timeline.
            if not persisted:
                flush_text()  # persist any text streamed before the abort
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

    async def _log_usage(
        self,
        run_id: str,
        conversation_id: str,
        usage: dict[str, int],
    ) -> None:
        """Log this turn's token usage and the conversation's running aggregate."""
        logger.info(
            "turn_tokens",
            run_id=run_id,
            conversation_id=conversation_id,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        try:
            totals = await self.run_service.token_totals(conversation_id)
            logger.info(
                "conversation_tokens",
                conversation_id=conversation_id,
                turns=totals["runs"],
                prompt_tokens=totals["prompt_tokens"],
                completion_tokens=totals["completion_tokens"],
                total_tokens=totals["total_tokens"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("conversation_tokens_failed", error=str(exc))
