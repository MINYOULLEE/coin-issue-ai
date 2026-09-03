begin;

alter table public.telegram_notify_state
  add column if not exists last_system_error_fingerprint text,
  add column if not exists last_system_error_alerted_at timestamptz;

commit;
