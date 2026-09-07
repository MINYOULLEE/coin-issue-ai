-- Display-only status correction. Preserve the owner-controlled live switches.
update public.plan_b_trading_state
set validation_status = 'stage66_profit_lock_deployed_live_health_ok_pending_natural_signal',
    updated_at = clock_timestamp()
where id = 'singleton'
  and strategy_id = 'b_profit_lock_stage66';
