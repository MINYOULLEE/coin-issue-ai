begin;

alter table public.trade_signals
  drop constraint if exists trade_signals_signal_type_check;

alter table public.trade_signals
  add constraint trade_signals_signal_type_check
  check (
    signal_type = any (
      array[
        'swing'::text,
        'tactical'::text,
        'candidate_a_big'::text,
        'candidate_a_small'::text,
        'research_a_big'::text,
        'research_a_small'::text
      ]
    )
  );

alter table public.real_trades
  drop constraint if exists real_trades_signal_type_check;

alter table public.real_trades
  add constraint real_trades_signal_type_check
  check (
    signal_type = any (
      array[
        'swing'::text,
        'tactical'::text,
        'candidate_a_big'::text,
        'candidate_a_small'::text,
        'research_a_big'::text,
        'research_a_small'::text
      ]
    )
  );

commit;
