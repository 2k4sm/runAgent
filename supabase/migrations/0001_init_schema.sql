-- runAgent — initial schema
-- Run via the Supabase SQL editor or `supabase db push`.
-- Four tables, all keyed to auth.users.

-- ---------------------------------------------------------------------------
-- Helper: updated_at trigger function
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- conversations
-- ---------------------------------------------------------------------------
create table if not exists public.conversations (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users (id) on delete cascade,
    title       text not null default 'New conversation',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists idx_conversations_user_id
    on public.conversations (user_id);

create trigger trg_conversations_updated_at
    before update on public.conversations
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- runs
-- ---------------------------------------------------------------------------
create table if not exists public.runs (
    id                 uuid primary key default gen_random_uuid(),
    conversation_id    uuid not null references public.conversations (id) on delete cascade,
    user_id            uuid not null references auth.users (id) on delete cascade,
    status             text not null default 'pending'
                       check (status in ('pending', 'running', 'completed', 'failed')),
    model              text,
    prompt_tokens      integer not null default 0,
    completion_tokens  integer not null default 0,
    error              text,
    created_at         timestamptz not null default now(),
    completed_at       timestamptz
);

create index if not exists idx_runs_conversation_id on public.runs (conversation_id);
create index if not exists idx_runs_user_id on public.runs (user_id);

-- ---------------------------------------------------------------------------
-- messages
-- ---------------------------------------------------------------------------
create table if not exists public.messages (
    id               uuid primary key default gen_random_uuid(),
    conversation_id  uuid not null references public.conversations (id) on delete cascade,
    run_id           uuid references public.runs (id) on delete set null,
    user_id          uuid not null references auth.users (id) on delete cascade,
    role             text not null
                     check (role in ('user', 'assistant', 'system', 'tool')),
    agent            text,
    content          text,
    metadata         jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now()
);

create index if not exists idx_messages_conversation_id on public.messages (conversation_id);
create index if not exists idx_messages_run_id on public.messages (run_id);

-- ---------------------------------------------------------------------------
-- assets
-- ---------------------------------------------------------------------------
create table if not exists public.assets (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references auth.users (id) on delete cascade,
    conversation_id  uuid references public.conversations (id) on delete cascade,
    run_id           uuid references public.runs (id) on delete set null,
    source           text not null check (source in ('upload', 'generated')),
    file_name        text not null,
    file_type        text not null,
    file_size        bigint not null default 0,
    -- Object path within the public Supabase Storage bucket.
    storage_path     text not null,
    created_at       timestamptz not null default now()
);

create index if not exists idx_assets_user_id on public.assets (user_id);
create index if not exists idx_assets_conversation_id on public.assets (conversation_id);
create index if not exists idx_assets_run_id on public.assets (run_id);
