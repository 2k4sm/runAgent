-- runAgent — run timeline
-- Each run now carries its full message+event timeline in a single jsonb
-- column, replacing the standalone `messages` table.

-- ---------------------------------------------------------------------------
-- runs.data — one chronologically ordered array of message and event entries.
-- ---------------------------------------------------------------------------
alter table public.runs
    add column if not exists data jsonb not null default '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- Drop the messages table — superseded by runs.data.
-- `cascade` removes idx_messages_* along with it. `assets` is untouched: it
-- references runs, not messages.
-- ---------------------------------------------------------------------------
drop table if exists public.messages cascade;
