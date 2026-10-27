-- Transactional authorization test. No test users, rows, or object metadata survive rollback.
begin;
insert into auth.users(id, aud, role, email, created_at, updated_at)
values ('11111111-1111-4111-8111-111111111111','authenticated','authenticated','apprentice-rls-a@example.invalid',now(),now()),
       ('22222222-2222-4222-8222-222222222222','authenticated','authenticated','apprentice-rls-b@example.invalid',now(),now());
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}',true);
insert into public.protocol_records(id,name,definition,provenance)
values ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','RLS probe','{}','synthetic');
insert into public.run_records(id,protocol_id,name,source_run_id,provenance,payload)
values ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','RLS probe','sample-probe','synthetic','{}');
insert into public.recordings(name,object_path,kind,size_bytes,mime_type)
values ('probe.mp4','11111111-1111-4111-8111-111111111111/probe.mp4','expert',16,'video/mp4');
insert into storage.objects(bucket_id,name,metadata)
values ('recordings','11111111-1111-4111-8111-111111111111/probe.mp4','{}');
do $$ begin
  if (select count(*) from public.run_records) <> 1 then raise exception 'Owner cannot read own run'; end if;
  if (select count(*) from public.recordings) <> 1 then raise exception 'Owner cannot read recording'; end if;
end $$;
select set_config('request.jwt.claims','{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}',true);
do $$ begin
  if (select count(*) from public.protocol_records) <> 0 then raise exception 'Protocol leaked to peer'; end if;
  if (select count(*) from public.run_records) <> 0 then raise exception 'Run leaked to peer'; end if;
  if (select count(*) from public.recordings) <> 0 then raise exception 'Recording leaked to peer'; end if;
  if (select count(*) from storage.objects where bucket_id='recordings') <> 0 then raise exception 'File metadata leaked to peer'; end if;
  begin
    insert into public.protocol_records(owner_id,name,definition,provenance)
    values ('11111111-1111-4111-8111-111111111111','Spoof','{}','manual');
    raise exception 'Owner spoofing succeeded';
  exception when insufficient_privilege then null; end;
  begin
    insert into storage.objects(bucket_id,name,metadata)
    values ('recordings','11111111-1111-4111-8111-111111111111/spoof.mp4','{}');
    raise exception 'Cross-owner storage upload succeeded';
  exception when insufficient_privilege then null; end;
  update public.run_records set name='Spoof' where id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  if found then raise exception 'Cross-owner update succeeded'; end if;
  delete from public.run_records where id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
  if found then raise exception 'Cross-owner delete succeeded'; end if;
end $$;
reset role;
set local role anon;
do $$ begin
  begin
    perform * from public.run_records;
    raise exception 'Unauthenticated database access succeeded';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
rollback;
select 'Owner isolation, spoof protection, update/delete restrictions, private storage and anon denial passed; transaction rolled back.' as verification;
