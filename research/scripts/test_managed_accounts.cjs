const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const migration=fs.readFileSync('supabase/migrations/20260909074042_add_managed_bingx_accounts.sql','utf8');
const ui=fs.readFileSync('docs/managed-accounts.js','utf8');
const webhook=fs.readFileSync('supabase/functions/telegram-bot-webhook/index.ts','utf8');
test('managed accounts are service-only and credentials are Vault references',()=>{
 assert.match(migration,/enable row level security/);
 assert.match(migration,/revoke all on public\.managed_bingx_accounts from public, anon, authenticated/);
 assert.match(migration,/api_key_secret_id uuid/);assert.match(migration,/secret_key_secret_id uuid/);
 assert.doesNotMatch(migration,/api_key\s+text|secret_key\s+text/i);
 assert.match(migration,/not live_enabled or \(status = 'connected' and api_key_secret_id is not null\)/);
});
test('dashboard lazily loads trades only when an account is opened',()=>{
 assert.match(ui,/addEventListener\('toggle'/);assert.match(ui,/if\(d\.open\)maTrades/);
 assert.match(ui,/managed_dashboard_session/);assert.match(ui,/managed-account-read/);
});
test('Telegram managed account alerts are opt-in and histories are click driven',()=>{
 assert.match(webhook,/alerts_enabled/);assert.match(webhook,/callback_data:`managed:/);
 assert.match(webhook,/^.*이 계정들의 자동 거래 알림은 기본 OFF입니다.*$/m);
});
