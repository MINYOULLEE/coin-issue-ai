import test from 'node:test';
import assert from 'node:assert/strict';
import {webhookSecret,validWebhookSecret} from '../../supabase/functions/_shared/telegram_webhook_auth.mjs';
test('missing optional webhook environment uses deterministic bot-bound secret, never empty auth',()=>{
 const s=webhookSecret('fixture-bot-token');assert.match(s,/^[a-f0-9]{64}$/);
 assert.equal(s,webhookSecret('fixture-bot-token'));assert.notEqual(s,webhookSecret('another-bot'));
 assert.equal(validWebhookSecret(s,s),true);assert.equal(validWebhookSecret(null,s),false);
 assert.equal(validWebhookSecret('', ''),false);assert.equal(validWebhookSecret('wrong',s),false);
 assert.equal(webhookSecret('fixture','configured-value'),'configured-value');assert.throws(()=>webhookSecret(''));
});
