begin;

do $$
declare d text;
begin
  select pg_get_functiondef('public.plan_b_publish_opportunities(bigint,jsonb)'::regprocedure) into d;
  if position('all twelve decisions required' in d) = 0 then
    raise exception 'unexpected Stage45 publish function';
  end if;
  if position('<>11' in d) = 0 then
    raise exception 'legacy eleven-decision guard not found';
  end if;
  execute replace(d, '<>11', '<>12');
end $$;

commit;
