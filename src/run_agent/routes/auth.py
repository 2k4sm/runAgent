"""Auth routes.

Sign-in/sign-up happen client-side via the Supabase SDK. The backend only
verifies the resulting JWT, so this route just exposes the current user.
"""

from fastapi import APIRouter, Depends

from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser

router = APIRouter()


@router.get("/me", response_model=CurrentUser)
async def get_me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user
