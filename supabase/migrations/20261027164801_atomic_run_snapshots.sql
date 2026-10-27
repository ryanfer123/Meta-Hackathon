-- Invoker functions preserve RLS and make a saved protocol/run an atomic unit.
create function public.save_run_snapshot(snapshot jsonb)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare protocol_uuid uuid; run_uuid uuid;
begin
  if auth.uid() is null then raise exception 'Sign in to save a run' using errcode='42501'; end if;
  if jsonb_typeof(snapshot) <> 'object'
     or jsonb_typeof(snapshot->'protocol') <> 'object'
     or jsonb_typeof(snapshot->'events') <> 'array'
     or jsonb_typeof(snapshot->'frames') <> 'array'
     or octet_length(snapshot::text) > 4000000 then
    raise exception 'Invalid run snapshot' using errcode='22023';
  end if;
  insert into public.protocol_records(name,definition,provenance)
  values (snapshot#>>'{protocol,name}',snapshot->'protocol',
    case when snapshot->>'provenance'='synthetic' then 'synthetic' else 'recording' end)
  returning id into protocol_uuid;
  insert into public.run_records(protocol_id,name,source_run_id,provenance,payload,chain_root)
  values(protocol_uuid,snapshot->>'name',snapshot->>'id',snapshot->>'provenance',snapshot,snapshot->>'chain_root')
  returning id into run_uuid;
  return run_uuid;
end $$;
revoke all on function public.save_run_snapshot(jsonb) from public, anon;
grant execute on function public.save_run_snapshot(jsonb) to authenticated;

create function public.delete_run_snapshot(run_uuid uuid)
returns void language plpgsql security invoker set search_path = '' as $$
declare protocol_uuid uuid;
begin
  if auth.uid() is null then raise exception 'Sign in to delete a run' using errcode='42501'; end if;
  delete from public.run_records where id=run_uuid returning protocol_id into protocol_uuid;
  if protocol_uuid is not null and not exists(select 1 from public.run_records where protocol_id=protocol_uuid) then
    delete from public.protocol_records where id=protocol_uuid;
  end if;
end $$;
revoke all on function public.delete_run_snapshot(uuid) from public, anon;
grant execute on function public.delete_run_snapshot(uuid) to authenticated;
