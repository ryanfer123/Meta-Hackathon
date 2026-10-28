-- All fixtures and temporary config changes are rolled back; no model calls.
begin;
insert into auth.users(id,aud,role,email,created_at,updated_at) values
('77777777-7777-4777-8777-777777777777','authenticated','authenticated','native-budget-test@example.invalid',now(),now());
insert into private.model_budget_config(singleton,key_sha256) values(true,encode(extensions.digest('test-only-native-key','sha256'),'hex'))
 on conflict(singleton) do update set key_sha256=excluded.key_sha256;
-- Tests lock the config row rather than deleting or replacing any real reservations.
select singleton from private.model_budget_config where singleton=true for update;
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"77777777-7777-4777-8777-777777777777","role":"authenticated"}',true);
do $$ begin
 begin
  perform public.reserve_model_budget('wrong','native','sam',.01,50);
  raise exception 'Wrong server key accepted';
 exception when insufficient_privilege then null; end;
 -- Four-argument SQL and older RPC callers remain valid through defaults.
 perform public.reserve_model_budget('test-only-native-key','legacy','spark',.01);
 perform public.reserve_model_budget('test-only-native-key','frames','sam',.2,1000,2,1000,2000,0,40,60);
 perform public.reserve_model_budget('test-only-native-key','frames','sam',.2,1000,2,1000,2000,0,40,60);
 begin
  perform public.reserve_model_budget('test-only-native-key','frames','sam',.0002,1,2,1000,2000,0,40,60);
  raise exception 'Frame cap not enforced';
 exception when raise_exception then if sqlerrm='Frame cap not enforced' then raise; end if; end;
 begin
  perform public.reserve_model_budget('test-only-native-key','images','sam',.0025,0,2,1000,2000,0,40,60);
  raise exception 'Image cap not enforced';
 exception when raise_exception then if sqlerrm='Image cap not enforced' then raise; end if; end;
 begin
  perform public.reserve_model_budget('test-only-native-key','day','voice',.01,0,2,.000001,2000,800,40,60);
  raise exception 'Daily cost cap not enforced';
 exception when raise_exception then if sqlerrm='Daily cost cap not enforced' then raise; end if; end;
 perform public.reserve_model_budget('test-only-native-key','overrun','sam',.01,50,2,1000);
 begin
  perform public.reconcile_sam_budget('wrong','overrun',50,75);
  raise exception 'Wrong reconciliation key accepted';
 exception when insufficient_privilege then null; end;
 perform public.reconcile_sam_budget('test-only-native-key','overrun',50,75);
 begin
  perform public.reserve_model_budget('test-only-native-key','another-run','spark',.01,0,2,1000);
  raise exception 'Global day halt not enforced';
 exception when raise_exception then if sqlerrm='Global day halt not enforced' then raise; end if; end;
 begin
  perform * from private.model_reservations;
  raise exception 'Private ledger exposed';
 exception when insufficient_privilege then null; end;
end $$;
reset role;
do $$ begin
 if (select sum(processed_frames) from private.model_reservations where owner_id='77777777-7777-4777-8777-777777777777' and run='overrun')<>75 then
  raise exception 'Unexpected usage was not recorded';
 end if;
 if has_function_privilege('anon','public.reconcile_sam_budget(text,text,integer,integer)','execute') then
  raise exception 'Anonymous reconciliation allowed';
 end if;
end $$;
rollback;
select 'Native-frame/image caps, secret gate, legacy calls, daily halt and private ledger isolation passed; all fixtures rolled back.' as verification;
