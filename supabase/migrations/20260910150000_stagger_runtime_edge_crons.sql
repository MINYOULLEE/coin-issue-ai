begin;

-- All six minute jobs previously started on the same second.  Preserve every
-- job, credential expression and timeout, but spread the Edge requests through
-- the minute so a transient queue cannot consume B's five-minute entry window.
do $$
declare
  current_command text;
  item record;
begin
  for item in
    select * from (values
      (6, 5),   -- close management remains first priority
      (5, 15),  -- execute after the strategy has published the hour
      (2, 35),  -- notify after trade state is settled
      (3, 50)   -- capture the current minute's completed HTTP responses
    ) as delays(job_id, delay_seconds)
  loop
    select command into current_command from cron.job where jobid=item.job_id;
    if current_command is null then raise exception 'runtime cron job % missing',item.job_id; end if;
    if current_command like '%pg_sleep(%' then raise exception 'runtime cron job % already staggered',item.job_id; end if;
    perform cron.alter_job(item.job_id,
      command := format('select pg_sleep(%s);%s',item.delay_seconds,current_command));
  end loop;
end;
$$;

commit;
