alter table public.media_collector_settings
  add column if not exists news_sources jsonb not null default '[]'::jsonb;

alter table public.media_collector_settings
  drop constraint if exists media_collector_settings_news_sources_array_check,
  add constraint media_collector_settings_news_sources_array_check
    check (jsonb_typeof(news_sources) = 'array' and jsonb_array_length(news_sources) <= 50);

comment on column public.media_collector_settings.news_sources is
  'Administrator-managed News/RSS publisher allowlist. Thumbnail preview permission is stored separately per publisher.';
