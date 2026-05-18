"""MCP server management — CRUD, connection testing, and OAuth orchestration.

This is the boundary that owns the encrypted `auth_config` column: it encrypts
on write, decrypts on read, and never returns secrets to callers.
"""

import json
import time
from typing import Any
from urllib.parse import urlparse

from run_agent.config import constants
from run_agent.config.logging import get_logger
from run_agent.config.settings import settings
from run_agent.repositories.mcp_repo import MCPServerRepository
from run_agent.schemas.mcp import MCPServerCreate, MCPServerUpdate
from run_agent.services.mcp_client import MCPClient
from run_agent.services.mcp_oauth import (
    MCPOAuthError,
    build_authorization_url,
    discover,
    exchange_code,
    make_state,
    pkce_pair,
    refresh_token,
    register_client,
    server_id_from_state,
)
from run_agent.utils import crypto
from run_agent.utils.favicon import favicon_url

logger = get_logger(__name__)

# Refresh an OAuth access token if it expires within this many seconds.
_TOKEN_REFRESH_SKEW = 60


class MCPServerService:
    def __init__(self) -> None:
        self.repo = MCPServerRepository()

    # -- config encryption ---------------------------------------------------
    def _decrypt_config(self, row: dict[str, Any]) -> dict[str, Any]:
        blob = row.get("auth_config")
        if not blob:
            return {}
        try:
            return json.loads(crypto.decrypt(blob))
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_auth_config_decrypt_failed", error=str(exc))
            return {}

    def _encrypt_config(self, config: dict[str, Any]) -> str:
        return crypto.encrypt(json.dumps(config))

    def _to_out(self, row: dict[str, Any]) -> dict[str, Any]:
        """Project a row to the client-safe shape (no secrets)."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "url": row["url"],
            "transport": row["transport"],
            "auth_type": row["auth_type"],
            "enabled": row["enabled"],
            "status": row["status"],
            "status_detail": row.get("status_detail"),
            "icon_url": favicon_url(row["url"]),
            "tools": row.get("tools_cache") or [],
            "created_at": row.get("created_at"),
        }

    def _redirect_uri(self) -> str:
        return f"{settings.public_base_url}{settings.api_prefix}/mcp/oauth/callback"

    # -- auth resolution -----------------------------------------------------
    async def resolve_headers(self, row: dict[str, Any]) -> dict[str, str]:
        """Return the HTTP headers needed to connect to this server.

        For OAuth servers this refreshes the access token if it is near expiry.
        """
        auth_type = row["auth_type"]
        if auth_type == constants.MCP_AUTH_NONE:
            return {}

        config = self._decrypt_config(row)
        if auth_type == constants.MCP_AUTH_HEADER:
            return {str(k): str(v) for k, v in (config.get("headers") or {}).items()}

        # OAuth
        oauth = config.get("oauth") or {}
        tokens = oauth.get("tokens") or {}
        if not tokens.get("access_token"):
            raise MCPOAuthError("This server has not been authorized yet.")

        if (
            tokens.get("expires_at", 0) < time.time() + _TOKEN_REFRESH_SKEW
            and tokens.get("refresh_token")
        ):
            tokens = await refresh_token(
                oauth["token_endpoint"],
                client_id=oauth["client_id"],
                client_secret=oauth.get("client_secret"),
                refresh_token=tokens["refresh_token"],
                resource=row["url"],
            )
            oauth["tokens"] = tokens
            config["oauth"] = oauth
            await self.repo.update(
                row["id"], {"auth_config": self._encrypt_config(config)}
            )
        return {"Authorization": f"Bearer {tokens['access_token']}"}

    # -- connection testing --------------------------------------------------
    async def _test_and_persist(self, row: dict[str, Any]) -> dict[str, Any]:
        """Connect, discover tools, and persist status + tool cache."""
        try:
            headers = await self.resolve_headers(row)
            async with MCPClient(row["url"], headers, row["transport"]) as client:
                tools = await client.list_tools()
                detected = client.detected_transport or row["transport"]
                server_name = client.server_name
                server_instructions = client.server_instructions
            patch = {
                "status": constants.MCP_CONNECTED,
                "status_detail": None,
                "transport": detected,
                "tools_cache": [
                    {"name": t["name"], "description": t["description"]}
                    for t in tools
                ],
            }
            # Adopt the server's self-reported identity (discovered on connect).
            if server_name:
                patch["name"] = server_name
            if server_instructions and server_instructions.strip():
                patch["description"] = server_instructions.strip()[:500]
        except Exception as exc:  # noqa: BLE001
            logger.warning("mcp_test_failed", server=row["id"], error=str(exc))
            patch = {
                "status": constants.MCP_ERROR,
                "status_detail": str(exc)[:500],
            }
        return await self.repo.update(row["id"], patch) or {**row, **patch}

    # -- CRUD ----------------------------------------------------------------
    async def list_servers(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.repo.list_for_user(user_id)
        return [self._to_out(r) for r in rows]

    async def list_active_rows(self, user_id: str) -> list[dict[str, Any]]:
        """Full rows for enabled + connected servers (for the agent catalog)."""
        rows = await self.repo.list_for_user(user_id)
        return [
            r
            for r in rows
            if r["enabled"] and r["status"] == constants.MCP_CONNECTED
        ]

    async def get_row(self, server_id: str, user_id: str) -> dict[str, Any]:
        row = await self.repo.get_for_user(server_id, user_id)
        if not row:
            raise ValueError(f"MCP server {server_id} not found")
        return row

    async def create(
        self, user_id: str, body: MCPServerCreate
    ) -> dict[str, Any]:
        auth_config: str | None = None
        if body.auth_type == constants.MCP_AUTH_HEADER:
            auth_config = self._encrypt_config(
                {"headers": {h.key: h.value for h in body.headers}}
            )
        status = (
            constants.MCP_NEEDS_AUTH
            if body.auth_type == constants.MCP_AUTH_OAUTH
            else constants.MCP_DISCONNECTED
        )
        # Name/description are discovered from the server on first connect;
        # until then use a placeholder derived from the URL host.
        placeholder_name = urlparse(body.url).hostname or body.url
        row = await self.repo.create({
            "user_id": user_id,
            "name": placeholder_name,
            "description": None,
            "url": body.url,
            "transport": "auto",
            "auth_type": body.auth_type,
            "auth_config": auth_config,
            "enabled": True,
            "status": status,
            "tools_cache": [],
        })
        # Non-OAuth servers can be connected and discovered right away.
        if body.auth_type != constants.MCP_AUTH_OAUTH:
            row = await self._test_and_persist(row)
        return self._to_out(row)

    async def update(
        self, server_id: str, user_id: str, body: MCPServerUpdate
    ) -> dict[str, Any]:
        row = await self.get_row(server_id, user_id)
        patch: dict[str, Any] = {}
        if body.name is not None:
            patch["name"] = body.name
        if body.description is not None:
            patch["description"] = body.description
        if body.enabled is not None:
            patch["enabled"] = body.enabled
        headers_changed = (
            body.headers is not None
            and row["auth_type"] == constants.MCP_AUTH_HEADER
        )
        if headers_changed and body.headers is not None:
            patch["auth_config"] = self._encrypt_config(
                {"headers": {h.key: h.value for h in body.headers}}
            )
        updated = await self.repo.update(server_id, patch) or row
        if headers_changed:
            updated = await self._test_and_persist(updated)
        return self._to_out(updated)

    async def delete(self, server_id: str, user_id: str) -> None:
        await self.get_row(server_id, user_id)  # ownership check
        await self.repo.delete(server_id)

    async def test(self, server_id: str, user_id: str) -> dict[str, Any]:
        row = await self.get_row(server_id, user_id)
        return self._to_out(await self._test_and_persist(row))

    # -- OAuth ---------------------------------------------------------------
    async def oauth_start(self, server_id: str, user_id: str) -> str:
        """Discover, register a client, and return the authorization URL."""
        row = await self.get_row(server_id, user_id)
        meta = await discover(row["url"])
        registration_endpoint = meta.get("registration_endpoint")
        if not registration_endpoint:
            raise MCPOAuthError(
                "This server does not support dynamic client registration; "
                "OAuth cannot be set up automatically."
            )
        redirect_uri = self._redirect_uri()
        creds = await register_client(registration_endpoint, redirect_uri)
        verifier, challenge = pkce_pair()
        state = make_state(server_id)
        config = {
            "oauth": {
                "client_id": creds["client_id"],
                "client_secret": creds.get("client_secret"),
                "token_endpoint": meta["token_endpoint"],
                "verifier": verifier,
                "state": state,
                "redirect_uri": redirect_uri,
            }
        }
        await self.repo.update(server_id, {
            "auth_config": self._encrypt_config(config),
            "status": constants.MCP_NEEDS_AUTH,
        })
        return build_authorization_url(
            meta,
            client_id=creds["client_id"],
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
            resource=row["url"],
        )

    async def oauth_complete(self, state: str, code: str) -> None:
        """Exchange the authorization code for tokens (callback path)."""
        server_id = server_id_from_state(state)
        row = await self.repo.get(server_id)
        if not row:
            raise ValueError("Unknown MCP server for this OAuth callback")
        config = self._decrypt_config(row)
        oauth = config.get("oauth") or {}
        if oauth.get("state") != state:
            raise MCPOAuthError("OAuth state mismatch — please retry the connection.")

        tokens = await exchange_code(
            oauth["token_endpoint"],
            client_id=oauth["client_id"],
            client_secret=oauth.get("client_secret"),
            code=code,
            code_verifier=oauth["verifier"],
            redirect_uri=oauth["redirect_uri"],
            resource=row["url"],
        )
        oauth["tokens"] = tokens
        config["oauth"] = oauth
        row = await self.repo.update(
            server_id, {"auth_config": self._encrypt_config(config)}
        ) or row
        # Discover tools now that the server is authorized.
        await self._test_and_persist(row)
