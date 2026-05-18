"""MCP server request/response models."""

from datetime import datetime

from pydantic import BaseModel


class MCPHeader(BaseModel):
    """A single auth header key/value pair."""

    key: str
    value: str


class MCPServerCreate(BaseModel):
    # Name and description are discovered from the server itself, not supplied.
    url: str
    # none | header | oauth
    auth_type: str = "none"
    # Only for auth_type == "header".
    headers: list[MCPHeader] = []


class MCPServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    headers: list[MCPHeader] | None = None


class MCPToolInfo(BaseModel):
    name: str
    description: str | None = None


class MCPServerOut(BaseModel):
    """A server as returned to the client — never includes secrets."""

    id: str
    name: str
    description: str | None = None
    url: str
    transport: str
    auth_type: str
    enabled: bool
    status: str
    status_detail: str | None = None
    # Live favicon URL for the server's domain (fetched on-demand by the UI).
    icon_url: str | None = None
    tools: list[MCPToolInfo] = []
    created_at: datetime | None = None


class OAuthStartOut(BaseModel):
    authorization_url: str
