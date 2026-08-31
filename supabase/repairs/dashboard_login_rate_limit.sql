create table if not exists public.dashboard_login_limits (
 plan text not null check(plan in ('A','B')),
 client_hash text not null check(client_hash ~ '^[0-9a-f]{64}$'),
 attempts integer not null check(attempts between 1 and 6),
 expires_at timestamptz not null,
 primary key(plan,client_hash)
);
alter table public.dashboard_login_limits enable row level security;
revoke all on public.dashboard_login_limits from public,anon,authenticated;
grant select,insert,update,delete on public.dashboard_login_limits to service_role;
create index if not exists dashboard_login_limits_expiry on public.dashboard_login_limits(expires_at);
create or replace function public.dashboard_login_attempt(p_plan text,p_key text)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare at_time timestamptz:=clock_timestamp(); n integer; until_time timestamptz;
begin
 if p_plan is null or p_plan not in ('A','B') or p_key is null or p_key !~ '^[0-9a-f]{64}$' then raise exception 'invalid login bucket'; end if;
 delete from public.dashboard_login_limits where expires_at<at_time-interval '1 day';
 insert into public.dashboard_login_limits as limits(plan,client_hash,attempts,expires_at)
 values(p_plan,p_key,1,at_time+interval '15 minutes')
 on conflict(plan,client_hash) do update set
 attempts=case when limits.expires_at<=at_time then 1 else least(limits.attempts+1,6) end,
 expires_at=case when limits.expires_at<=at_time then at_time+interval '15 minutes' else limits.expires_at end
 returning attempts,expires_at into n,until_time;
 return jsonb_build_object('allowed',n<=5,'retry_after',case when n<=5 then 0 else greatest(1,ceil(extract(epoch from until_time-at_time)))::integer end);
end $$;
revoke all on function public.dashboard_login_attempt(text,text) from public,anon,authenticated;
grant execute on function public.dashboard_login_attempt(text,text) to service_role;
