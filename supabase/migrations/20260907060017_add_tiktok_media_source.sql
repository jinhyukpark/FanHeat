-- Allow approved TikTok Research API results in the collector tables.

alter table public.media_collection_jobs
  drop constraint if exists media_collection_jobs_source_check;
alter table public.media_collection_jobs
  add constraint media_collection_jobs_source_check
  check (source in ('youtube', 'tiktok', 'x', 'news', 'artist'));

alter table public.media_collection_rules
  drop constraint if exists media_collection_rules_source_check;
alter table public.media_collection_rules
  add constraint media_collection_rules_source_check
  check (source in ('youtube', 'tiktok', 'x', 'news', 'artist'));

alter table public.media_raw_items
  drop constraint if exists media_raw_items_source_check;
alter table public.media_raw_items
  add constraint media_raw_items_source_check
  check (source in ('youtube', 'tiktok', 'x', 'news'));

alter table public.media_items
  drop constraint if exists media_items_source_check;
alter table public.media_items
  add constraint media_items_source_check
  check (source in ('youtube', 'tiktok', 'x', 'news'));
