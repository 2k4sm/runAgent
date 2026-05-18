"""Conversation CRUD routes."""

from fastapi import APIRouter, Depends

from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser
from run_agent.schemas.chat import RunOut
from run_agent.schemas.conversation import ConversationCreate, ConversationOut
from run_agent.services.conversation_service import ConversationService
from run_agent.services.run_service import RunService

router = APIRouter()


@router.post("", response_model=ConversationOut)
async def create_conversation(
    body: ConversationCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    return await ConversationService().create(user.id, body.title, body.id)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await ConversationService().list_for_user(user.id)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    return await ConversationService().get(conversation_id, user.id)


@router.get("/{conversation_id}/runs", response_model=list[RunOut])
async def list_runs(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """Return every run in the conversation, each with its ordered timeline."""
    await ConversationService().get(conversation_id, user.id)  # ownership check
    return await RunService().run_repo.list_for_conversation(conversation_id)


@router.delete("/{conversation_id}/runs/{run_id}")
async def delete_run(
    conversation_id: str,
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a single run — used to discard a failed run before retrying it."""
    await ConversationService().get(conversation_id, user.id)  # ownership check
    await RunService().delete(run_id, user.id)
    return {"status": "deleted"}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    await ConversationService().delete(conversation_id, user.id)
    return {"status": "deleted"}
