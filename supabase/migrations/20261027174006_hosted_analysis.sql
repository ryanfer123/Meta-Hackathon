-- Durable private jobs and a server-authorized global model reservation ledger.
create table public.analysis_jobs (
 id text primary key check(id ~ '^[a-f0-9]{32}$'),
 owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 kind text not null check(kind in ('learn','run')),
 status text not null check(status in ('processing','ready','error')),
 result jsonb not null default '{}'::jsonb check(jsonb_typeof(result)='object'),
 artifact_path text,
 created_at timestamptz not null default now()
);
alter table public.analysis_jobs enable row level security;
revoke all on public.analysis_jobs from anon;
grant select,insert,update,delete on public.analysis_jobs to authenticated;
create policy job_owner on public.analysis_jobs to authenticated using(owner_id=(select auth.uid())) with check(owner_id=(select auth.uid()));
create index jobs_owner_created on public.analysis_jobs(owner_id,created_at desc);
create unique index one_active_job_per_owner on public.analysis_jobs(owner_id) where status='processing';
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('analysis-artifacts','analysis-artifacts',false,115343360,array['application/zip']);
create policy artifact_read on storage.objects for select to authenticated using(bucket_id='analysis-artifacts' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy artifact_insert on storage.objects for insert to authenticated with check(bucket_id='analysis-artifacts' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy artifact_update on storage.objects for update to authenticated using(bucket_id='analysis-artifacts' and (storage.foldername(name))[1]=(select auth.uid())::text) with check(bucket_id='analysis-artifacts' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy artifact_delete on storage.objects for delete to authenticated using(bucket_id='analysis-artifacts' and (storage.foldername(name))[1]=(select auth.uid())::text);

create schema if not exists private;
revoke all on schema private from public,anon,authenticated;
create table private.model_budget_config(singleton bool primary key default true check(singleton),key_sha256 text not null);
create table private.model_reservations(id bigint generated always as identity primary key,day date not null default current_date,owner_id uuid not null,run text not null,kind text not null,cost numeric not null check(cost>0));
alter table private.model_budget_config enable row level security;
alter table private.model_reservations enable row level security;
create index reservation_day on private.model_reservations(day);
create index reservation_run on private.model_reservations(owner_id,run);
-- Definer is needed only to lock/read the private account-wide ledger. The caller must
-- have a valid user JWT AND the backend-only key; neither clients nor anon can reserve.
create function public.reserve_model_budget(server_key text,run_id text,call_kind text,reserved_usd numeric)
returns void language plpgsql security definer set search_path='' as $$
declare expected text;
begin
 select key_sha256 into expected from private.model_budget_config where singleton=true for update;
 if auth.uid() is null or expected is null or pg_catalog.encode(extensions.digest(server_key,'sha256'),'hex') is distinct from expected then
  raise exception 'Server authorization required' using errcode='42501';
 end if;
 if run_id !~ '^[a-zA-Z0-9_-]{1,100}$' or call_kind not in ('spark','sam','voice') or reserved_usd<=0 or reserved_usd>1 then
  raise exception 'Invalid reservation' using errcode='22023';
 end if;
 if (select coalesce(sum(cost),0) from private.model_reservations where day=current_date)+reserved_usd>5
 or (select coalesce(sum(cost),0) from private.model_reservations where owner_id=auth.uid() and run=run_id)+reserved_usd>2
 or (call_kind='spark' and (select count(*) from private.model_reservations where day=current_date and kind='spark')>=60)
 or (call_kind='sam' and (select count(*) from private.model_reservations where owner_id=auth.uid() and run=run_id and kind='sam')>=800)
 then raise exception 'Model request budget reached; try another day or review the recording' using errcode='P0001'; end if;
 insert into private.model_reservations(owner_id,run,kind,cost) values(auth.uid(),run_id,call_kind,reserved_usd);
end $$;
revoke all on function public.reserve_model_budget(text,text,text,numeric) from public,anon;
grant execute on function public.reserve_model_budget(text,text,text,numeric) to authenticated;
