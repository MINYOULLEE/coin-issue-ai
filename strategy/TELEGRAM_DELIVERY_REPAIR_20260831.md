# Telegram receive and trade-delivery repair — 2026-08-31

## Root cause and repair

`getWebhookInfo` showed one pending update and `403 Forbidden`. TELEGRAM_WEBHOOK_SECRET was absent in deployed environments, while the old handler compared the incoming header against an empty string. Outbound notification delivery continued, but incoming menu requests failed authentication.

The handler and registration now share a domain-separated HMAC secret derived from the existing bot token when the optional configured secret is absent. Explicit configured secrets remain supported. Neither tokens nor derived secrets are returned. Empty/incorrect authentication remains denied. Webhook URL is fixed to this project's existing endpoint, and queued updates are preserved (`drop_pending_updates=false`). No polling or `getUpdates` was enabled.

Scheduler-authenticated operational actions: `webhook_status`, `repair_webhook`, and `test_overview` (only A or B and the existing approved owner chat). These cannot submit trades or change trading switches.

## Verification

- Webhook v22; notification engine v28.
- Re-registered webhook successfully; pending queue fell from 1 to 0 and current status omitted the prior delivery error.
- Live B overview test returned HTTP200, replied=true, Telegram message_id=223 (request 22486). This was a real B account read and message, not a simulated trade.
- Automatic notification state updated after deployment at 11:24:04 UTC.
- 92 Node regression tests passed, including delayed entries/already-closed fills, out-of-order A settlement, existing B settlement and webhook secret validation.

## Trade notification handling

A/B entry and rejection delivery now use per-trade markers instead of dropping later status transitions below a global ID watermark. A close delivery now uses per-trade markers instead of a global closed-time cutoff; B already had per-trade close delivery. Entries require an exchange order ID and a positive entry price. Close notices require actual positive close price and finite settled PnL; A additionally requires exchange-history settlement confirmation.

Migration `telegram_trade_delivery_receipts` only adds delivery columns and seeds historical delivery baselines from the old cursors to avoid replaying old notifications. Seeded markers are migration baselines, not proof of historical Telegram delivery. It does not edit fills, PnL, strategies, account credentials or live switches.

Notifications follow the regular scheduler and exchange settlement: they are not guaranteed simultaneous with a fill. A network failure after Telegram accepts a message but before its marker is saved can still cause a duplicate retry; exactly-once delivery is not claimed. Partial-fill-by-partial-fill reporting and manual exchange trades not represented in the bot's trading ledger are not certified by this repair.

A/B ON states remain unchanged. Prior news-source HTTP403 and diagnostic-versus-operational error classification issues are separate and unresolved.
