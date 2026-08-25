begin;

alter table public.trade_signals drop constraint if exists trade_signals_signal_type_check;
alter table public.trade_signals add constraint trade_signals_signal_type_check check (
  signal_type = any (array['swing','tactical','candidate_a_big','candidate_a_small','research_a_big','research_a_small','strategy_a','strategy_b','strategy_c','strategy_d','strategy_f','strategy_g']::text[])
);

alter table public.real_trades drop constraint if exists real_trades_signal_type_check;
alter table public.real_trades add constraint real_trades_signal_type_check check (
  signal_type = any (array['swing','tactical','candidate_a_big','candidate_a_small','research_a_big','research_a_small','strategy_a','strategy_b','strategy_c','strategy_d','strategy_f','strategy_g']::text[])
);

commit;
