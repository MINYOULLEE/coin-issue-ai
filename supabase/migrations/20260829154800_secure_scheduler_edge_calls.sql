-- Keep privileged cron-triggered functions off the public invocation path.
-- The key is generated inside Postgres and is never committed or returned to
-- clients. Both pg_cron and the service-role Edge Functions can read it.
insert into public.private_runtime_secrets (id, secret_value, updated_at)
values (
  'scheduler_auth',
  jsonb_build_object('key', encode(gen_random_bytes(32), 'hex')),
  now()
)
on conflict (id) do nothing;

alter table public.private_runtime_secrets enable row level security;
revoke all on table public.private_runtime_secrets from public, anon, authenticated;
grant select on table public.private_runtime_secrets to service_role;

select cron.alter_job(
  1,
  command := $command$
    select net.http_post(
      url := 'https://ljazcstmwtuhideaarti.supabase.co/functions/v1/coin-collector',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'apikey', 'sb_publishable_a-LZ7__bpIa6j8C7Bjdr1Q_aQJJbdVz',
        'x-scheduler-key', (select secret_value ->> 'key' from public.private_runtime_secrets where id = 'scheduler_auth')
      ),
      body := jsonb_build_object('scheduled_at', now()),
      timeout_milliseconds := 50000
    ) as request_id;
  $command$
);

select cron.alter_job(
  2,
  command := $command$
    select net.http_post(
      url := 'https://ljazcstmwtuhideaarti.supabase.co/functions/v1/telegram-trade-notify',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'apikey', 'sb_publishable_a-LZ7__bpIa6j8C7Bjdr1Q_aQJJbdVz',
        'x-scheduler-key', (select secret_value ->> 'key' from public.private_runtime_secrets where id = 'scheduler_auth')
      ),
      body := jsonb_build_object('scheduled_at', now()),
      timeout_milliseconds := 15000
    ) as request_id;
  $command$
);
