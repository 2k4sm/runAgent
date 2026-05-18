-- runAgent — MCP servers
-- Stores each user's connected MCP (Model Context Protocol) servers.
-- Run via the Supabase SQL editor or `supabase db push`.

create table if not exists public.mcp_servers (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references auth.users (id) on delete cascade,
    name          text not null,
    description   text,
    url           text not null,
    -- auto | streamable_http | sse
    transport     text not null default 'auto',
    auth_type     text not null default 'none'
                  check (auth_type in ('none', 'header', 'oauth')),
    -- Fernet-encrypted JSON blob: headers for header auth; client creds +
    -- OAuth tokens + PKCE/state for oauth. Never returned to the client.
    auth_config   text,
    enabled       boolean not null default true,
    -- disconnected | connected | needs_auth | error
    status        text not null default 'disconnected',
    status_detail text,
    -- Discovered tools: [{name, description}]
    tools_cache   jsonb not null default '[]'::jsonb,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists idx_mcp_servers_user_id on public.mcp_servers (user_id);

create trigger trg_mcp_servers_updated_at
    before update on public.mcp_servers
    for each row execute function public.set_updated_at();
