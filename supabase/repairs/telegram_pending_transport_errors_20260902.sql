begin;

alter table public.telegram_notify_state
  add column if not exists pending_transport_errors jsonb not null default '[]'::jsonb;

commit;
