-- Delivery markers only; never change trading state, fills, sizes or PnL.
alter table public.real_trades add column if not exists telegram_entry_notified_at timestamptz;
alter table public.real_trades add column if not exists telegram_rejection_notified_at timestamptz;
alter table public.real_trades add column if not exists telegram_close_notified_at timestamptz;
alter table public.plan_b_real_trades add column if not exists telegram_entry_notified_at timestamptz;
alter table public.plan_b_real_trades add column if not exists telegram_rejection_notified_at timestamptz;
-- Preserve the old delivery baseline once, avoiding replay of historical alerts.
-- These markers represent migration baseline, not new Telegram delivery receipts.
update public.real_trades set telegram_entry_notified_at=now()
 where telegram_entry_notified_at is null and status in ('open','closing','closed')
 and id <= (select last_trade_id from public.telegram_notify_state where id='singleton');
update public.real_trades set telegram_rejection_notified_at=now()
 where telegram_rejection_notified_at is null and status='rejected'
 and id <= (select last_trade_id from public.telegram_notify_state where id='singleton');
update public.real_trades set telegram_close_notified_at=now()
 where telegram_close_notified_at is null and status='closed'
 and close_reason='BingX positionHistory 주문별 동기화'
 and closed_at <= (select last_closed_at from public.telegram_notify_state where id='singleton');
update public.plan_b_real_trades set telegram_entry_notified_at=now()
 where telegram_entry_notified_at is null and status in ('open','closing','closed')
 and id <= (select last_pb_trade_id from public.telegram_notify_state where id='singleton');
update public.plan_b_real_trades set telegram_rejection_notified_at=now()
 where telegram_rejection_notified_at is null and status='rejected'
 and id <= (select last_pb_trade_id from public.telegram_notify_state where id='singleton');
