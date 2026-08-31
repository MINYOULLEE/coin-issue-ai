import test from 'node:test';
import assert from 'node:assert/strict';
import {stableHealthAlerts as step} from '../../supabase/functions/_shared/news_alert_stability.mjs';
test('single news timeout and next-minute success never notify',()=>{let s=step({}, {'news:x':'timeout'},0);assert.deepEqual(s.active,{});s=step(s.stored,{},60000);assert.deepEqual(s.active,{});});
test('persistent news failure opens once; recovery needs two observations',()=>{let s=step({}, {'news:x':'timeout'},0);s=step(s.stored,{'news:x':'timeout'},60000);assert.deepEqual(s.active,{});s=step(s.stored,{'news:x':'timeout'},120000);assert.equal(s.active['news:x'],'timeout');s=step(s.stored,{'news:x':'HTTP 503'},180000);assert.equal(s.active['news:x'],'timeout');s=step(s.stored,{},240000);assert.ok(s.active['news:x']);s=step(s.stored,{},300000);assert.deepEqual(s.active,{});});
test('trade failures stay immediate and repeated calls cannot accelerate news threshold',()=>{let s=step({}, {'B:execute':'bad','news:x':'bad'},0);assert.equal(s.active['B:execute'],'bad');for(let i=1;i<10;i++)s=step(s.stored,{'news:x':'bad'},i*1000);assert.deepEqual(s.active,{});});
