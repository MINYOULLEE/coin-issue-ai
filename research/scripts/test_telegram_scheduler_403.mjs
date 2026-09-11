import test from 'node:test';
import assert from 'node:assert/strict';
import {transportErrorDisposition} from '../../supabase/functions/_shared/operational_health.mjs';

test('opaque scheduler 403 waits for recovery but persistent failures still alert',()=>{
 const now=Date.now(),error={source:'supabase-http',status_code:403,message:'{"ok":false}',created_at:new Date(now-60000).toISOString()};
 assert.equal(transportErrorDisposition({error,snapshot:{},bHealth:[],now}),'pending');
 assert.equal(transportErrorDisposition({error:{...error,created_at:new Date(now-240000).toISOString()},snapshot:{},bHealth:[],now}),'alert');
});
