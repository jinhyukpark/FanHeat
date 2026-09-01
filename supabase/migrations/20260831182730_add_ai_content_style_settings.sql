alter table public.media_collector_settings
  add column if not exists content_tone text not null default 'fan_20s',
  add column if not exists target_audience text not null default 'general_fans',
  add column if not exists body_lines smallint not null default 4,
  add column if not exists emoji_level text not null default 'light',
  add column if not exists hashtag_count smallint not null default 5;

alter table public.media_collector_settings
  drop constraint if exists media_collector_settings_content_tone_check,
  add constraint media_collector_settings_content_tone_check
    check (content_tone in ('teen_fan', 'fan_20s', 'calm_report', 'news_article', 'warm_community', 'witty_short')),
  drop constraint if exists media_collector_settings_target_audience_check,
  add constraint media_collector_settings_target_audience_check
    check (target_audience in ('teens', 'twenties', 'general_fans', 'industry', 'general_public')),
  drop constraint if exists media_collector_settings_body_lines_check,
  add constraint media_collector_settings_body_lines_check check (body_lines between 1 and 12),
  drop constraint if exists media_collector_settings_emoji_level_check,
  add constraint media_collector_settings_emoji_level_check check (emoji_level in ('none', 'light', 'active')),
  drop constraint if exists media_collector_settings_hashtag_count_check,
  add constraint media_collector_settings_hashtag_count_check check (hashtag_count between 0 and 15);

comment on column public.media_collector_settings.content_tone is 'AI draft writing tone preset selected by the collector administrator';
comment on column public.media_collector_settings.target_audience is 'Intended readership for generated AI drafts';
comment on column public.media_collector_settings.body_lines is 'Target number of body lines for generated AI drafts';
comment on column public.media_collector_settings.emoji_level is 'Emoji usage level for generated AI drafts';
comment on column public.media_collector_settings.hashtag_count is 'Target maximum number of hashtags for generated AI drafts';
