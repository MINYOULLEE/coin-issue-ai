// Post-fix verification; preserve the original RESULTS.json audit evidence.
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const {aEntryAdmission}=await import('../../supabase/functions/_shared/a_recovery_policy.mjs');
 const boundary=Date.parse('2026-09-15T00:59:59.999Z');
 const signal={id:1,symbol:'XRP',side:'short',status:'active',signal_type:'answer_mdd30',signal_model_version:'answer_mdd30_stage184_v1',strategy_epoch:'answer_mdd30_stage75_2026_09_08',created_at:'2026-09-15T01:00:01Z',entry_metrics:{strategy_config:{base_exposure_multiplier:.15}}};
 const cases=[{name:'legacy orphan same decision',hours:2,side:'short',status:'retry_pending',expected:true},{name:'next daily boundary passed',hours:25,side:'short',status:'retry_pending',expected:false},{name:'direction changed',hours:2,side:'long',status:'retry_pending',expected:false},{name:'completed decision',hours:2,side:'short',status:'completed',expected:false},{name:'future boundary',hours:-1,side:'short',status:'retry_pending',expected:false}];
 const rows=cases.map(c=>{const result=aEntryAdmission(signal,{hourly_audit:{status:c.status,closed_at:new Date(boundary).toISOString(),assets:[{symbol:'XRP',signal_id:1,answer:{side:c.side,exposure:.15}}]}},boundary+c.hours*3600000);assert.equal(result.allowed,c.expected,c.name);return {...c,result};});
 const result={id:'A-STAGE185-RECOVERY-VERIFICATION',live_changes:false,rows,passing:rows.length,failed:0};
 fs.mkdirSync('research/results/a_stage185_recovery_audit',{recursive:true});
 fs.writeFileSync('research/results/a_stage185_recovery_audit/VERIFICATION.json',JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
