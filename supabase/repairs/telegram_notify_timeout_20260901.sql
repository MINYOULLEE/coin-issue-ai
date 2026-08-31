-- Preserve one-minute cadence, auth and target; allow transient DNS latency.
do $$
declare j record;
begin
 select jobid,command into strict j from cron.job where jobname='telegram-trade-notify-every-minute';
 if position('timeout_milliseconds := 15000' in j.command)=0 then raise exception 'Unexpected timeout configuration'; end if;
 perform cron.alter_job(j.jobid,command:=replace(j.command,'timeout_milliseconds := 15000','timeout_milliseconds := 45000'));
end $$;
