-- Artist profile imports and refreshes share the collector job infrastructure,
-- but do not create raw media rows. Extend only the job/rule discriminators.

alter table public.media_collection_jobs
  drop constraint if exists media_collection_jobs_source_check;

alter table public.media_collection_jobs
  add constraint media_collection_jobs_source_check
  check (source in ('youtube', 'x', 'news', 'artist'));

alter table public.media_collection_jobs
  drop constraint if exists media_collection_jobs_status_check;

alter table public.media_collection_jobs
  add constraint media_collection_jobs_status_check
  check (status in ('pending', 'running', 'needs_attention', 'completed', 'failed', 'cancelled'));

alter table public.media_collection_rules
  drop constraint if exists media_collection_rules_source_check;

alter table public.media_collection_rules
  add constraint media_collection_rules_source_check
  check (source in ('youtube', 'x', 'news', 'artist'));
