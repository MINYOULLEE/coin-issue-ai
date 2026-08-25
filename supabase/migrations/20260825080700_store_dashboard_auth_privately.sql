begin;

create table if not exists public.private_runtime_secrets (
  id text primary key,
  secret_value jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.private_runtime_secrets enable row level security;

revoke all on table public.private_runtime_secrets from anon, authenticated;
grant select, insert, update on table public.private_runtime_secrets to service_role;

commit;
