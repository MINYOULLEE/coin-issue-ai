-- B Stage112 execution repair: owner activity must not keep the automatic
-- strategy paused, and already missed signals must not remain active.
update public.plan_b_signals
   set status='expired',
       dispatch_block_reason=coalesce(dispatch_block_reason,'expired_before_dispatch'),
       dispatch_checked_at=coalesce(dispatch_checked_at,clock_timestamp()),
       updated_at=clock_timestamp()
 where status='active'
   and dispatched_at is null
   and entry_deadline<clock_timestamp();

with automatic_closed as (
  select coalesce(sum(net_pnl_usd),0) pnl
    from public.plan_b_real_trades
   where status='closed'
     and control_marker=1
     and net_pnl_usd is not null
), repaired as (
  select greatest(0.01,s.starting_capital_usd+a.pnl) strategy_equity
    from public.plan_b_trading_state s cross join automatic_closed a
   where s.id='singleton'
)
update public.plan_b_trading_state s
   set risk_equity_peak_usdt=greatest(s.starting_capital_usd,r.strategy_equity),
       risk_last_equity_usdt=r.strategy_equity,
       risk_pause_until=null,
       risk_updated_at=clock_timestamp(),
       validation_status='stage112_deployed_pending_natural_live_validation_after_risk_isolation_repair',
       updated_at=clock_timestamp()
  from repaired r
 where s.id='singleton';

comment on column public.plan_b_trading_state.risk_last_equity_usdt is
  'Automatic B sleeve equity used by Stage112 drawdown guard; excludes owner control_marker=2 trades and cash movements.';
