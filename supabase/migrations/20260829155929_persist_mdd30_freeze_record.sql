create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.strategy_freeze_records (
  freeze_id text primary key,
  strategy_id text not null,
  standard jsonb not null,
  reproduced_replay jsonb not null,
  answer_trees_sha256 text not null,
  git_commit text not null,
  local_files text[] not null,
  frozen_at timestamptz not null default now()
);

revoke all on table private.strategy_freeze_records from public, anon, authenticated;
grant usage on schema private to service_role;
grant select on table private.strategy_freeze_records to service_role;

insert into private.strategy_freeze_records (
  freeze_id, strategy_id, standard, reproduced_replay,
  answer_trees_sha256, git_commit, local_files, frozen_at
)
values (
  'mdd30_final_2026_08_29',
  'answer_mdd30',
  '{"assets":["BTC","ETH","XRP","TRX","SOL"],"independent_tree_count":5,"decision_hour_utc":0,"decision_hour_asia_bangkok":7,"exchange_leverage":10,"max_gross_exposure":1.6,"fixed_take_profit":false,"fixed_stop_loss":false,"exit_mode":"daily_answer_rebalance","sizing_mode":"live_bingx_equity_compounding"}'::jsonb,
  '{"range":["2021-08-28","2026-08-29"],"method":"hourly_mark","decision_hour_utc":0,"fee_per_turnover":0.0004,"compound_return_pct":257597.52,"max_drawdown_pct":-35.53,"verification_status":"reproduced_from_current_source_and_downloaded_market_data"}'::jsonb,
  '9A483FD33C540F6601B01901143313B81C89E8C3A9CCD257141F86694F34E31B',
  'db86c08',
  array[
    'strategy/mdd30_standard.json',
    'strategy/mdd30_freeze_audit_2026-08-29.md',
    'research/results/mdd30_baseline_replay.json',
    'supabase/functions/coin-collector/answer_trees.ts'
  ],
  '2026-08-29T15:53:00Z'::timestamptz
)
on conflict (freeze_id) do update set
  standard = excluded.standard,
  reproduced_replay = excluded.reproduced_replay,
  answer_trees_sha256 = excluded.answer_trees_sha256,
  git_commit = excluded.git_commit,
  local_files = excluded.local_files,
  frozen_at = excluded.frozen_at;
