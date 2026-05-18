"""OAuth 2.1 helpers for connecting to MCP servers.

Implements the MCP authorization flow with plain `httpx`: metadata discovery,
Dynamic Client Registration, PKCE, and the authorization-code + refresh-token
grants. `MCPServerService` orchestrates persistence; this module is stateless.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from run_agent.config.logging import get_logger

logger = get_logger(__name__)

_DISCOVERY_HEADERS = {
    "Accept": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


class MCPOAuthError(Exception):
    """Raised when the OAuth flow cannot be completed."""


def pkce_pair() -> tuple[str, str]:
    """Return a (code_verifier, code_challenge) PKCE pair (S256)."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def make_state(server_id: str) -> str:
    """Build an OAuth `state` that carries the server id plus a CSRF nonce."""
    return f"{server_id}.{secrets.token_urlsafe(16)}"


def server_id_from_state(state: str) -> str:
    """Extract the server id encoded into a `state` value."""
    return state.split(".", 1)[0]


async def _get_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url, headers=_DISCOVERY_HEADERS)
    response.raise_for_status()
    return response.json()


async def discover(server_url: str) -> dict[str, Any]:
    """Discover the authorization-server metadata for an MCP server.

    Follows the protected-resource metadata to the authorization server, then
    fetches its metadata. Falls back to treating the server origin as the
    authorization server.
    """
    parsed = urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        auth_server = origin
        try:
            prm = await _get_json(
                client, f"{origin}/.well-known/oauth-protected-resource"
            )
            servers = prm.get("authorization_servers") or []
            if servers:
                auth_server = str(servers[0]).rstrip("/")
        except httpx.HTTPError:
            pass  # No protected-resource metadata — assume origin is the AS.

        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ):
            try:
                meta = await _get_json(client, f"{auth_server}{path}")
                if meta.get("authorization_endpoint") and meta.get("token_endpoint"):
                    return meta
            except httpx.HTTPError:
                continue

    raise MCPOAuthError(
        "Could not discover the MCP server's OAuth metadata. The server may not "
        "support OAuth, or may require a manually configured auth header instead."
    )


async def register_client(
    registration_endpoint: str, redirect_uri: str
) -> dict[str, Any]:
    """Dynamically register a client and return its credentials."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            registration_endpoint,
            json={
                "client_name": "runAgent",
                "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        response.raise_for_status()
        return response.json()


def build_authorization_url(
    meta: dict[str, Any],
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    resource: str,
) -> str:
    """Build the URL the user is redirected to in order to grant access."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    scopes = meta.get("scopes_supported")
    if isinstance(scopes, list) and scopes:
        params["scope"] = " ".join(str(s) for s in scopes)
    return f"{meta['authorization_endpoint']}?{urlencode(params)}"


def _tokens_from_response(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a token-endpoint response into our stored token shape."""
    expires_in = int(data.get("expires_in", 3600) or 3600)
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": int(time.time()) + expires_in,
    }


def _auth_data(client_id: str, client_secret: str | None) -> dict[str, str]:
    data = {"client_id": client_id}
    if client_secret:
        data["client_secret"] = client_secret
    return data


async def exchange_code(
    token_endpoint: str,
    *,
    client_id: str,
    client_secret: str | None,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    resource: str,
) -> dict[str, Any]:
    """Exchange an authorization code for tokens."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "resource": resource,
                **_auth_data(client_id, client_secret),
            },
        )
        if response.status_code >= 400:
            raise MCPOAuthError(f"Token exchange failed: {response.text}")
        return _tokens_from_response(response.json())


async def refresh_token(
    token_endpoint: str,
    *,
    client_id: str,
    client_secret: str | None,
    refresh_token: str,
    resource: str,
) -> dict[str, Any]:
    """Use a refresh token to obtain a fresh access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "resource": resource,
                **_auth_data(client_id, client_secret),
            },
        )
        if response.status_code >= 400:
            raise MCPOAuthError(f"Token refresh failed: {response.text}")
        tokens = _tokens_from_response(response.json())
        # Some servers omit the refresh token on refresh — keep the old one.
        if not tokens["refresh_token"]:
            tokens["refresh_token"] = refresh_token
        return tokens
