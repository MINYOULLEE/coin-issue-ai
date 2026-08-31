begin;
alter table public.telegram_notify_state add column if not exists health_alerts jsonb not null default '{}'::jsonb;
create or replace function public.capture_recent_http_errors() returns void language plpgsql security definer set search_path='' as $$
declare r record; j jsonb; failed boolean;
begin
 for r in select id,status_code,content,timed_out,error_msg,created from net._http_response where created>now()-interval '5 minutes' loop
  j:=null;
  begin j:=r.content::jsonb; exception when invalid_text_representation then j:=null; end;
  failed:=coalesce(r.status_code,0)>=400 or coalesce(r.timed_out,false) or r.error_msg is not null or j->>'ok'='false';
  if jsonb_typeof(j->'results')='array' then
   failed:=coalesce(failed,false) or exists(select 1 from jsonb_array_elements(j->'results') x where x->>'ok'='false' or (x->>'error') is not null);
  end if;
  if coalesce(failed,false) then
   insert into public.system_errors(source,status_code,message,fingerprint,created_at)
   values(case when j->>'plan'='B' then 'plan-b-http' else 'supabase-http' end,r.status_code,
     left(coalesce(r.error_msg,r.content,case when r.timed_out then 'HTTP timeout without status code' else 'HTTP request failed' end),1000),
     md5(r.id::text||':'||coalesce(r.status_code::text,'')||':'||coalesce(r.content,'')),r.created)
   on conflict(fingerprint) do nothing;
  end if;
 end loop;
end;
$$;
revoke all on function public.capture_recent_http_errors() from public,anon,authenticated;
grant execute on function public.capture_recent_http_errors() to service_role;
commit;
