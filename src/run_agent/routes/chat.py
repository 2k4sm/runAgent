"""Chat route — accepts a message and streams one run via SSE.

Each call creates a new run: one cycle of user message + events + assistant
message. The conversation is the thread that accumulates these runs.
"""

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from run_agent.middlewares.rate_limit import rate_limit
from run_agent.schemas.auth import CurrentUser
from run_agent.schemas.chat import ChatMessageIn
from run_agent.services.agent_service import AgentService
from run_agent.services.conversation_service import ConversationService
from run_agent.services.file_service import FileService
from run_agent.services.run_service import RunService
from run_agent.services.stream_service import StreamService

router = APIRouter()


@router.post("/message")
async def send_message(
    body: ChatMessageIn,
    user: CurrentUser = Depends(rate_limit),
) -> StreamingResponse:
    """Start a new run for the message and stream its events via SSE."""
    # Ownership check — raises if the conversation is not the caller's.
    await ConversationService().get(body.conversation_id, user.id)

    run_service = RunService()
    agent_service = AgentService()
    file_service = FileService()

    # Resolve attachments by id, scoped to the caller — raises before any
    # streaming begins if an id is unknown or not owned.
    attachment_records = [
        await file_service.get_asset(asset_id, user.id)
        for asset_id in body.attachment_ids
    ]

    run = await run_service.create_run(
        user_id=user.id, conversation_id=body.conversation_id
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event in agent_service.execute(
            run_id=run["id"],
            user_id=user.id,
            conversation_id=body.conversation_id,
            content=body.content,
            attachments=attachment_records,
            reasoning=body.reasoning,
            timezone=body.timezone,
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
