"""Supabase JWT verification dependency.

Supabase projects now sign user access tokens with asymmetric keys (ES256/RS256)
exposed via a JWKS endpoint. Older projects use a shared HS256 secret. This
dependency verifies both: it inspects the token header and picks the matching
strategy, so it keeps working regardless of how the project is configured.
"""

import time

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from run_agent.config.settings import settings
from run_agent.schemas.auth import CurrentUser

security = HTTPBearer()

# JWKS keys rarely change; cache them to avoid a network call per request.
_JWKS_TTL_SECONDS = 600
_jwks_cache: dict[str, object] = {"keys": [], "fetched_at": 0.0}


async def _fetch_jwks(force: bool = False) -> list[dict]:
    """Return the project's JWKS keys, refetching when the cache is stale."""
    now = time.time()
    cached_keys: list[dict] = _jwks_cache["keys"]  # type: ignore[assignment]
    cached_at: float = _jwks_cache["fetched_at"]  # type: ignore[assignment]

    if not force and cached_keys and now - cached_at < _JWKS_TTL_SECONDS:
        return cached_keys

    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers={"apikey": settings.supabase_anon_key})
        resp.raise_for_status()
        keys: list[dict] = resp.json().get("keys", [])

    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def _find_key(keys: list[dict], kid: str | None) -> dict | None:
    """Locate the JWK matching the token's `kid`."""
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


async def _decode_token(token: str) -> dict:
    """Verify a Supabase JWT and return its claims."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    if alg == "HS256":
        # Legacy projects: shared symmetric secret.
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )

    # Modern projects: asymmetric keys verified against the JWKS endpoint.
    kid = header.get("kid")
    keys = await _fetch_jwks()
    jwk = _find_key(keys, kid)
    if jwk is None:
        # The signing key may have rotated — refetch once before giving up.
        keys = await _fetch_jwks(force=True)
        jwk = _find_key(keys, kid)
    if jwk is None:
        raise JWTError(f"No matching JWKS key for kid={kid}")

    return jwt.decode(
        token,
        jwk,
        algorithms=[alg],
        audience="authenticated",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """Verify a Supabase JWT and return the authenticated user."""
    try:
        payload = await _decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503, detail="Unable to verify token signing keys"
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    return CurrentUser(
        id=user_id,
        email=payload.get("email"),
        role=payload.get("role"),
    )
