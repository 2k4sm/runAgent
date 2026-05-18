"""MCP server management routes."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from run_agent.config.settings import settings
from run_agent.middlewares.auth import get_current_user
from run_agent.schemas.auth import CurrentUser
from run_agent.schemas.mcp import (
    MCPServerCreate,
    MCPServerOut,
    MCPServerUpdate,
    OAuthStartOut,
)
from run_agent.services.mcp_oauth import MCPOAuthError
from run_agent.services.mcp_service import MCPServerService

router = APIRouter()


def _service() -> MCPServerService:
    return MCPServerService()


@router.get("/servers", response_model=list[MCPServerOut])
async def list_servers(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    return await _service().list_servers(user.id)


@router.post("/servers", response_model=MCPServerOut)
async def create_server(
    body: MCPServerCreate,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        return await _service().create(user.id, body)
    except MCPOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/servers/{server_id}", response_model=MCPServerOut)
async def update_server(
    server_id: str,
    body: MCPServerUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        return await _service().update(server_id, user.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        await _service().delete(server_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted"}


@router.post("/servers/{server_id}/test", response_model=MCPServerOut)
async def retest_server(
    server_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        return await _service().test(server_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/servers/{server_id}/oauth/start", response_model=OAuthStartOut)
async def oauth_start(
    server_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        url = await _service().oauth_start(server_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MCPOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"authorization_url": url}


def _callback_page(ok: bool, message: str) -> str:
    """A minimal page that notifies the opener window and closes itself."""
    origin = settings.cors_origins[0] if settings.cors_origins else "*"
    status = "connected" if ok else "error"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>MCP authorization</title></head>
<body style="font-family:system-ui;padding:2rem;text-align:center">
<p>{message}</p>
<script>
  try {{
    if (window.opener) {{
      window.opener.postMessage(
        {{ type: "mcp-oauth", status: "{status}" }}, "{origin}"
      );
    }}
  }} catch (e) {{}}
  setTimeout(function () {{ window.close(); }}, 1200);
</script>
</body></html>"""


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """OAuth redirect target — hit by the browser, not the SPA. No auth here;
    the request is validated via the signed `state` value."""
    if error or not code or not state:
        return HTMLResponse(
            _callback_page(False, f"Authorization failed: {error or 'missing code'}.")
        )
    try:
        await _service().oauth_complete(state, code)
    except (ValueError, MCPOAuthError) as exc:
        return HTMLResponse(_callback_page(False, f"Authorization failed: {exc}"))
    return HTMLResponse(
        _callback_page(True, "Connected. You can close this window.")
    )
