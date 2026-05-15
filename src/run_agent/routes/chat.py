"""Chat route — accepts a message and streams the agent pipeline via SSE."""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from run_agent.middlewares.rate_limit import rate_limit
from run_agent.schemas.auth import CurrentUser
from run_agent.services.agent_service import AgentService
from run_agent.services.conversation_service import ConversationService
from run_agent.services.file_service import FileService
from run_agent.services.run_service import RunService
from run_agent.services.stream_service import StreamService

router = APIRouter()


@router.post("/message")
async def send_message(
    content: str = Form(...),
    conversation_id: str = Form(...),
    attachments: list[UploadFile] | None = File(default=None),
    user: CurrentUser = Depends(rate_limit),
) -> StreamingResponse:
    """Accept a user message, run the agent pipeline, and stream events via SSE."""
    # Ownership check — raises if the conversation is not the caller's.
    await ConversationService().get(conversation_id, user.id)

    run_service = RunService()
    agent_service = AgentService()
    file_service = FileService()

    run = await run_service.create_run(user_id=user.id, conversation_id=conversation_id)

    attachment_records = []
    for file in attachments or []:
        file_bytes = await file.read()
        asset = await file_service.upload_attachment(
            user_id=user.id,
            conversation_id=conversation_id,
            file_name=file.filename or "unnamed",
            content=file_bytes,
            mime_type=file.content_type or "application/octet-stream",
        )
        attachment_records.append(asset)

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event in agent_service.execute(
            run_id=run["id"],
            user_id=user.id,
            conversation_id=conversation_id,
            content=content,
            attachments=attachment_records,
        ):
            yield StreamService.format(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
