"""Agent orchestration — runs the supervisor pipeline and persists results."""

import base64
import io
from collections.abc import AsyncGenerator
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
        """Run the supervisor pipeline, streaming SSE events and persisting state."""
        attachments = attachments or []
        # `usage` is filled in by each agent with exact provider-reported token
        # counts as the run progresses (see BaseAgent._accumulate_usage).
        context: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        # Read prior turns BEFORE persisting the new message, otherwise the
        # current message would appear twice in the LLM context.
        history = await self.run_service.history(conversation_id)

        await self.run_service.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=constants.ROLE_USER,
            content=content,
            metadata={"attachment_count": len(attachments)},
        )

        message_content = await build_multimodal_content(content, attachments)
        messages = [*history, {"role": "user", "content": message_content}]

        assistant_chunks: list[str] = []
        final_agent = constants.AGENT_SUPERVISOR

        try:
            supervisor = SupervisorAgent()
            async for event in supervisor.run(messages, context):
                if event.type == "chunk" and event.content:
                    assistant_chunks.append(event.content)
                    final_agent = event.agent
                yield event

            answer = "".join(assistant_chunks)
            if answer:
                await self.run_service.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=constants.ROLE_ASSISTANT,
                    content=answer,
                    run_id=run_id,
                    agent=final_agent,
                )
            usage = context["usage"]
            await self.run_service.complete_run(
                run_id,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("agent_execution_failed", run_id=run_id, error=str(exc))
            await self.run_service.fail_run(run_id, str(exc))
            yield SSEEvent(
                type="error",
                agent=final_agent,
                content="The agent encountered an error and could not complete.",
            )
            yield SSEEvent(type="done", agent=final_agent)
