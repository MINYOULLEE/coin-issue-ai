import {createHmac,timingSafeEqual} from 'node:crypto';
import {Buffer} from 'node:buffer';
export function webhookSecret(bot,configured=''){
 if(configured)return configured;
 if(!bot)throw Error('Telegram webhook authentication unavailable');
 return createHmac('sha256',bot).update('coin-issue-ai:telegram-webhook:v1').digest('hex');
}
export function validWebhookSecret(supplied,expected){
 if(!supplied||!expected)return false;
 const a=Buffer.from(supplied),b=Buffer.from(expected);
 return a.length===b.length&&timingSafeEqual(a,b);
}
