import test from 'node:test';
import assert from 'node:assert/strict';
import {errorText} from '../../supabase/functions/_shared/error_text.mjs';

test('structured Supabase errors do not become object Object',()=>{
 const text=errorText({code:'PGRST204',message:'column missing',details:'schema cache'});
 assert.match(text,/PGRST204/);
 assert.match(text,/column missing/);
 assert.doesNotMatch(text,/\[object Object\]/);
});

test('Error and circular values remain readable',()=>{
 assert.equal(errorText(new Error('network timeout')),'network timeout');
 const circular={message:null}; circular.self=circular;
 assert.equal(errorText(circular),'unserializable structured error');
});
