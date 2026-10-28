-- Native SAM reservations count billed frames separately from image requests.
-- Defaulted new arguments preserve existing four-argument callers during deployment.
alter table private.model_reservations
 add column processed_frames integer not null default 0 check(processed_frames>=0);
alter table private.model_budget_config add column halted_day date;

drop function public.reserve_model_budget(text,text,text,numeric);
create function public.reserve_model_budget(
 server_key text,run_id text,call_kind text,reserved_usd numeric,
 processed_frames integer default 0,
 max_run_usd numeric default 2,max_day_usd numeric default 5,
 max_sam_frames integer default 2000,max_sam_calls integer default 800,
 max_spark_calls integer default 40,max_spark_day integer default 60
) returns void language plpgsql security definer set search_path='' as $$
declare expected text; halted date; utc_day date := (pg_catalog.timezone('UTC',now()))::date;
begin
 select key_sha256,halted_day into expected,halted
 from private.model_budget_config where singleton=true for update;
 if auth.uid() is null or expected is null or
 pg_catalog.encode(extensions.digest(server_key,'sha256'),'hex') is distinct from expected then
  raise exception 'Server authorization required' using errcode='42501';
 end if;
 if run_id is null or run_id !~ '^[a-zA-Z0-9_-]{1,100}$'
 or call_kind is null or call_kind not in ('spark','sam','voice')
 or reserved_usd is null or reserved_usd<=0 or reserved_usd::text in ('NaN','Infinity','-Infinity')
 or processed_frames is null or processed_frames<0 or (call_kind<>'sam' and processed_frames<>0)
 or max_run_usd is null or max_run_usd<=0 or max_run_usd::text in ('NaN','Infinity','-Infinity')
 or max_day_usd is null or max_day_usd<=0 or max_day_usd::text in ('NaN','Infinity','-Infinity')
 or max_sam_frames is null or max_sam_frames<0 or max_sam_calls is null or max_sam_calls<0
 or max_spark_calls is null or max_spark_calls<0 or max_spark_day is null or max_spark_day<0 then
  raise exception 'Invalid reservation' using errcode='22023';
 end if;
 if halted=utc_day then
  raise exception 'SAM usage exceeded reservation; model requests halted for this UTC day' using errcode='P0001';
 end if;
 if (select coalesce(sum(cost),0) from private.model_reservations where day=utc_day)+reserved_usd>max_day_usd
 or (select coalesce(sum(cost),0) from private.model_reservations where owner_id=auth.uid() and run=run_id)+reserved_usd>max_run_usd
 or (call_kind='spark' and (
  (select count(*) from private.model_reservations where day=utc_day and kind='spark')>=max_spark_day
  or (select count(*) from private.model_reservations where owner_id=auth.uid() and run=run_id and kind='spark')>=max_spark_calls))
 or (call_kind='sam' and processed_frames=0 and
  (select count(*) from private.model_reservations where owner_id=auth.uid() and run=run_id and kind='sam' and model_reservations.processed_frames=0)>=max_sam_calls)
 or (call_kind='sam' and processed_frames>0 and (
  reserved_usd+0.000000001<processed_frames*0.0002
  or (select coalesce(sum(model_reservations.processed_frames),0) from private.model_reservations where owner_id=auth.uid() and run=run_id)+processed_frames>max_sam_frames))
 then raise exception 'Model request budget reached; review the recording or configured limits' using errcode='P0001'; end if;
 insert into private.model_reservations(day,owner_id,run,kind,cost,processed_frames)
 values(utc_day,auth.uid(),run_id,call_kind,reserved_usd,processed_frames);
end $$;
revoke all on function public.reserve_model_budget(text,text,text,numeric,integer,numeric,numeric,integer,integer,integer,integer) from public,anon;
grant execute on function public.reserve_model_budget(text,text,text,numeric,integer,numeric,numeric,integer,integer,integer,integer) to authenticated;

-- Reconciliation records unexpected billed usage even when it would exceed a cap,
-- then halts subsequent requests globally for the UTC day. Never refund attempts.
create function public.reconcile_sam_budget(
 server_key text,run_id text,reserved_frames integer,actual_frames integer
) returns void language plpgsql security definer set search_path='' as $$
declare expected text; utc_day date := (pg_catalog.timezone('UTC',now()))::date;
begin
 select key_sha256 into expected from private.model_budget_config where singleton=true for update;
 if auth.uid() is null or expected is null or
 pg_catalog.encode(extensions.digest(server_key,'sha256'),'hex') is distinct from expected then
  raise exception 'Server authorization required' using errcode='42501';
 end if;
 if run_id is null or run_id !~ '^[a-zA-Z0-9_-]{1,100}$'
 or reserved_frames is null or reserved_frames<0 or actual_frames is null or actual_frames<0 then
  raise exception 'Invalid reconciliation' using errcode='22023';
 end if;
 if actual_frames<=reserved_frames then return; end if;
 if not exists(select 1 from private.model_reservations
  where owner_id=auth.uid() and run=run_id and kind='sam' and day=utc_day
  and processed_frames>=reserved_frames and processed_frames>0) then
  raise exception 'No matching server reservation' using errcode='22023';
 end if;
 insert into private.model_reservations(day,owner_id,run,kind,cost,processed_frames)
 values(utc_day,auth.uid(),run_id,'sam_overrun',(actual_frames-reserved_frames)*0.0002,actual_frames-reserved_frames);
 update private.model_budget_config set halted_day=utc_day where singleton=true;
end $$;
revoke all on function public.reconcile_sam_budget(text,text,integer,integer) from public,anon;
grant execute on function public.reconcile_sam_budget(text,text,integer,integer) to authenticated;
