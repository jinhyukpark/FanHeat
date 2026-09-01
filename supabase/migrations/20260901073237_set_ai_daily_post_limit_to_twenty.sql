-- Raise every AI persona's daily post allowance to the existing maximum.
-- The publication worker reads this value dynamically for each publish run.
alter table public.ai_personas
  alter column daily_post_limit set default 20;

update public.ai_personas
set daily_post_limit = 20,
    updated_at = now()
where daily_post_limit is distinct from 20;
