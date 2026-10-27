-- Apprentice: private personal workspaces. Model/inference credentials are never stored here.
create table public.protocol_records (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 160),
  definition jsonb not null check (jsonb_typeof(definition) = 'object'),
  provenance text not null check (provenance in ('synthetic', 'recording', 'manual')),
  created_at timestamptz not null default now(),
  unique (id, owner_id)
);

create table public.run_records (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  protocol_id uuid not null,
  name text not null check (char_length(name) between 1 and 160),
  source_run_id text not null check (char_length(source_run_id) between 1 and 100),
  provenance text not null check (provenance in ('synthetic', 'live-recording')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 4000000),
  chain_root text check (chain_root is null or chain_root ~ '^[a-f0-9]{64}$'),
  created_at timestamptz not null default now(),
  foreign key (protocol_id, owner_id) references public.protocol_records(id, owner_id) on delete cascade
);

create table public.recordings (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 240),
  object_path text not null unique,
  kind text not null check (kind in ('expert', 'held_out', 'novice')),
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 52428800),
  mime_type text not null check (mime_type in ('video/mp4', 'video/quicktime')),
  status text not null default 'uploaded' check (status in ('uploaded', 'processing', 'ready', 'error')),
  created_at timestamptz not null default now(),
  check (split_part(object_path, '/', 1) = owner_id::text)
);

create index protocol_records_owner_created_idx on public.protocol_records(owner_id, created_at desc);
create index run_records_owner_created_idx on public.run_records(owner_id, created_at desc);
create index run_records_protocol_owner_idx on public.run_records(protocol_id, owner_id);
create index recordings_owner_created_idx on public.recordings(owner_id, created_at desc);

alter table public.protocol_records enable row level security;
alter table public.run_records enable row level security;
alter table public.recordings enable row level security;
revoke all on public.protocol_records, public.run_records, public.recordings from anon;
grant select, insert, update, delete on public.protocol_records, public.run_records, public.recordings to authenticated;

create policy "Owners read protocols" on public.protocol_records for select to authenticated using ((select auth.uid()) = owner_id);
create policy "Owners create protocols" on public.protocol_records for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy "Owners update protocols" on public.protocol_records for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy "Owners delete protocols" on public.protocol_records for delete to authenticated using ((select auth.uid()) = owner_id);
create policy "Owners read runs" on public.run_records for select to authenticated using ((select auth.uid()) = owner_id);
create policy "Owners create runs" on public.run_records for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy "Owners update runs" on public.run_records for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy "Owners delete runs" on public.run_records for delete to authenticated using ((select auth.uid()) = owner_id);
create policy "Owners read recordings" on public.recordings for select to authenticated using ((select auth.uid()) = owner_id);
create policy "Owners create recordings" on public.recordings for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy "Owners update recordings" on public.recordings for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy "Owners delete recordings" on public.recordings for delete to authenticated using ((select auth.uid()) = owner_id);

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('recordings', 'recordings', false, 52428800, array['video/mp4', 'video/quicktime']);

create policy "Owners read video files" on storage.objects for select to authenticated
using (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "Owners upload video files" on storage.objects for insert to authenticated
with check (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "Owners delete video files" on storage.objects for delete to authenticated
using (bucket_id = 'recordings' and (storage.foldername(name))[1] = (select auth.uid())::text);
