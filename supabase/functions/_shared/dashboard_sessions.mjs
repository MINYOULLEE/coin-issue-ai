import {createHmac,randomUUID,timingSafeEqual} from 'node:crypto';
import {Buffer} from 'node:buffer';
const TTL=4*60*60*1000;
export function createDashboardSessions(plan){
 if(!['A','B'].includes(plan))throw Error('invalid dashboard plan');
 const sign=(payload,secret)=>{if(typeof secret!=='string'||!secret)throw Error('missing session secret');return createHmac('sha256',secret).update(`coin-issue-dashboard:v2:${plan}:${payload}`).digest('base64url');};
 return {
  issue(secret,now=Date.now()){const p=Buffer.from(JSON.stringify({plan,version:2,iat:now,exp:now+TTL,nonce:randomUUID()})).toString('base64url');return p+'.'+sign(p,secret);},
  valid(token,secret,now=Date.now()){
   try{if(typeof token!=='string'||token.length>2048)return false;const parts=token.split('.');if(parts.length!==2)return false;const[p,s]=parts,expected=sign(p,secret);if(s.length!==expected.length||!timingSafeEqual(Buffer.from(s),Buffer.from(expected)))return false;
    const c=JSON.parse(Buffer.from(p,'base64url').toString('utf8'));return c.plan===plan&&c.version===2&&Number.isFinite(c.iat)&&Number.isFinite(c.exp)&&c.iat<=now+60000&&c.exp>now&&c.exp-c.iat===TTL;
   }catch{return false;}
  }
 };
}
export async function reserveLoginAttempt(req,plan,secret,rpc){
 if(!['A','B'].includes(plan)||!secret)throw Error('login protection unavailable');
 const ip=(req.headers.get('x-forwarded-for')||'unknown').split(',')[0].trim().slice(0,128);
 const key=createHmac('sha256',secret).update(`dashboard-login:${plan}:${ip}`).digest('hex');
 const result=await rpc({p_plan:plan,p_key:key});
 if(!result||typeof result.allowed!=='boolean'||!Number.isFinite(result.retry_after))throw Error('invalid login protection response');
 return result;
}
