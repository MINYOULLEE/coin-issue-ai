create table if not exists public.coin_snapshots (
  id text primary key,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.coin_snapshots enable row level security;
drop policy if exists "public can read live snapshot" on public.coin_snapshots;
create policy "public can read live snapshot" on public.coin_snapshots for select to anon using (id = 'live');
revoke insert, update, delete on public.coin_snapshots from anon;
grant select on public.coin_snapshots to anon;
