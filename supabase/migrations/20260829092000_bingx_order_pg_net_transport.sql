-- Keep BingX credentials/signing in the executor, but move the one POST that
-- crashes Supabase Edge onto the database's pg_net worker. The destination is
-- fixed and only service_role may enqueue or inspect a request.
create or replace function public.submit_bingx_order_transport(
  p_body jsonb,
  p_api_key text
) returns bigint
language plpgsql
security definer
set search_path = public, net, pg_temp
as $$
declare
  v_request_id bigint;
begin
  if coalesce(p_api_key, '') = '' or p_body is null then
    raise exception 'missing BingX transport input';
  end if;
  select net.http_post(
    url := 'https://open-api.bingx.com/openApi/swap/v2/trade/order',
    body := p_body,
    params := '{}'::jsonb,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Accept-Encoding', 'identity',
      'X-BX-APIKEY', p_api_key,
      'X-SOURCE-KEY', 'BX-AI-SKILL'
    ),
    timeout_milliseconds := 10000
  ) into v_request_id;
  return v_request_id;
end;
$$;

create or replace function public.get_bingx_order_transport(p_request_id bigint)
returns table(status_code integer, content text, timed_out boolean, error_msg text)
language sql
security definer
set search_path = public, net, pg_temp
as $$
  select r.status_code, r.content, r.timed_out, r.error_msg
  from net._http_response r
  where r.id = p_request_id
  limit 1
$$;

revoke all on function public.submit_bingx_order_transport(jsonb,text) from public, anon, authenticated;
revoke all on function public.get_bingx_order_transport(bigint) from public, anon, authenticated;
grant execute on function public.submit_bingx_order_transport(jsonb,text) to service_role;
grant execute on function public.get_bingx_order_transport(bigint) to service_role;

comment on function public.submit_bingx_order_transport(jsonb,text) is
  'Service-role-only fixed-destination BingX live order transport via pg_net.';
