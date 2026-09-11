begin;

-- Stage112 changed the live strategy/version/prefix.  Keep the atomic database
-- boundary in lockstep so the first hourly publish and the first real order do
-- not continue to validate the retired Stage93 identifiers.
do $$
declare
  definition text;
begin
  select pg_get_functiondef('public.plan_b_publish_opportunities(bigint,jsonb)'::regprocedure)
    into definition;
  if definition not like '%b_algo_ada_stage93_v1%'
     or definition not like '%b_algo_ada_stage93%'
     or definition not like '%pb93:%' then
    raise exception 'unexpected plan_b_publish_opportunities source';
  end if;
  definition := replace(replace(replace(definition,
    'b_algo_ada_stage93_v1', 'b_regime_guard_stage112_v1'),
    'b_algo_ada_stage93', 'b_regime_guard_stage112'),
    'pb93:', 'pb112:');
  execute definition;

  select pg_get_functiondef('public.plan_b_reserve_intents(jsonb,numeric,numeric,numeric,timestamp with time zone)'::regprocedure)
    into definition;
  if definition not like '%b_algo_ada_stage93_v1%'
     or definition not like '%b_algo_ada_stage93%'
     or definition not like '%pb93-%' then
    raise exception 'unexpected plan_b_reserve_intents source';
  end if;
  definition := replace(replace(replace(definition,
    'b_algo_ada_stage93_v1', 'b_regime_guard_stage112_v1'),
    'b_algo_ada_stage93', 'b_regime_guard_stage112'),
    'pb93-', 'pb112-');
  execute definition;

  select pg_get_functiondef('public.plan_b_claim_intent(text)'::regprocedure)
    into definition;
  if definition not like '%b_algo_ada_stage93%' then
    raise exception 'unexpected plan_b_claim_intent source';
  end if;
  definition := replace(definition,
    'b_algo_ada_stage93', 'b_regime_guard_stage112');
  execute definition;
end;
$$;

alter table public.plan_b_execution_intents
  drop constraint if exists plan_b_execution_intents_client_order_id_check;
alter table public.plan_b_execution_intents
  add constraint plan_b_execution_intents_client_order_id_check
  check (client_order_id ~ '^pb(16|26|35|45|66|93|112)-[0-9]+$');

commit;
