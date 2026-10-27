-- Exercise the public invoker RPCs with JWT owner claims, then roll everything back.
begin;
insert into auth.users(id,aud,role,email,created_at,updated_at)
values ('33333333-3333-4333-8333-333333333333','authenticated','authenticated','apprentice-rpc@example.invalid',now(),now());
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}',true);
do $$
declare run_uuid uuid; count_before integer;
begin
  select count(*) into count_before from public.protocol_records;
  begin
    perform public.save_run_snapshot('{"id":"test","name":"Bad","protocol":{"name":"Bad"},"provenance":"synthetic"}');
    raise exception 'Missing event/frame arrays accepted';
  exception when invalid_parameter_value then null; end;
  if (select count(*) from public.protocol_records) <> count_before then raise exception 'Failed save left a protocol'; end if;
  begin
    perform public.save_run_snapshot('{"id":"test","name":"Bad","protocol":{"name":"Bad"},"provenance":"unsupported","events":[],"frames":[]}');
    raise exception 'Invalid provenance accepted';
  exception when check_violation then null; end;
  if (select count(*) from public.protocol_records) <> count_before then raise exception 'Failed second insert was not rolled back'; end if;
  run_uuid := public.save_run_snapshot('{"id":"test","name":"Saved test","protocol":{"name":"Test protocol"},"provenance":"synthetic","events":[],"frames":[]}');
  if not exists(select 1 from public.run_records where id=run_uuid and owner_id=auth.uid()) then raise exception 'Owner snapshot absent'; end if;
  perform public.delete_run_snapshot(run_uuid);
  if exists(select 1 from public.run_records where id=run_uuid) then raise exception 'Run deletion failed'; end if;
  if (select count(*) from public.protocol_records) <> count_before then raise exception 'Unused protocol not cleaned up'; end if;
end $$;
reset role;
rollback;
select 'Snapshot validation, atomic rollback, owner save and paired deletion passed; transaction rolled back.' as verification;
