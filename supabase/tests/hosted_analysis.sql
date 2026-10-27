begin;
insert into auth.users(id,aud,role,email,created_at,updated_at) values
('55555555-5555-4555-8555-555555555555','authenticated','authenticated','budget-probe@example.invalid',now(),now());
insert into private.model_budget_config(singleton,key_sha256) values(true,encode(extensions.digest('test-only-server-key','sha256'),'hex')) on conflict(singleton) do update set key_sha256=excluded.key_sha256;
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"55555555-5555-4555-8555-555555555555","role":"authenticated"}',true);
do $$ begin
 begin
  perform public.reserve_model_budget('wrong-key','test','spark',.25);
  raise exception 'Wrong server key accepted';
 exception when insufficient_privilege then null; end;
 perform public.reserve_model_budget('test-only-server-key','test','spark',1);
 perform public.reserve_model_budget('test-only-server-key','test','spark',1);
 begin
  perform public.reserve_model_budget('test-only-server-key','test','spark',.01);
  raise exception 'Run budget exceeded';
 exception when raise_exception then
  if sqlerrm='Run budget exceeded' then raise; end if;
 end;
 insert into public.analysis_jobs(id,kind,status) values(repeat('b',32),'learn','ready');
 begin
  perform * from private.model_reservations;
  raise exception 'Private reservation ledger exposed';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claims','{"sub":"66666666-6666-4666-8666-666666666666","role":"authenticated"}',true);
do $$ begin
 if exists(select 1 from public.analysis_jobs where id=repeat('b',32)) then raise exception 'Peer job visible'; end if;
 update public.analysis_jobs set result='{"spoof":true}' where id=repeat('b',32);
 if found then raise exception 'Peer job editable'; end if;
end $$;
reset role;
rollback;
select 'Server-key reservation enforcement, run cap, ledger isolation and owner-scoped jobs passed; all fixtures rolled back.' as verification;
