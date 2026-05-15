-- runAgent — Supabase Storage bucket for user attachments and generated files.
-- Public bucket: objects are accessible to anyone with the URL. The backend
-- uses the service-role key for uploads/deletes.

insert into storage.buckets (id, name, public)
values ('assets', 'assets', true)
on conflict (id) do update set public = true;
