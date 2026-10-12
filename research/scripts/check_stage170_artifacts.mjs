import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html=fs.readFileSync('docs/index.html','utf8');
let scripts=0;for(const m of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)){if(m[1].trim()){new vm.Script(m[1]);scripts++;}}
assert(html.includes('B플랜 추천 · Stage170 공격형'));
assert(html.includes('+1,976,478.03%'));
assert(html.includes('새 유지 정책의 온전한 7년 결과 없음'));
const code=fs.readFileSync('supabase/functions/managed-account-executor/index.ts','utf8');
assert(code.includes('B:B_STANDARD.standard_version'));
assert(code.includes('const A_VERSION="mdd30_5x_c_controller_stage184_v1"'));
console.log(JSON.stringify({html_scripts_parsed:scripts,b_stage170_ui:true,managed_b_uses_canonical_version:true,a_stage184_unchanged:true}));
