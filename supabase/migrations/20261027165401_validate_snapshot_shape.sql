-- Invoker functions preserve RLS and make a saved protocol/run an atomic unit.
create or replace function public.save_run_snapshot(snapshot jsonb)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare protocol_uuid uuid; run_uuid uuid;
begin
  if auth.uid() is null then raise exception 'Sign in to save a run' using errcode='42501'; end if;
  if jsonb_typeof(snapshot) is distinct from 'object'
     or not (snapshot ?& array['id','name','protocol','events','frames','provenance'])
     or jsonb_typeof(snapshot->'protocol') is distinct from 'object'
     or jsonb_typeof(snapshot->'events') is distinct from 'array'
     or jsonb_typeof(snapshot->'frames') is distinct from 'array'
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
