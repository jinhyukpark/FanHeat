alter table public.media_collector_settings
  add column if not exists language_filter_mode varchar(16) not null default 'strict';

alter table public.media_collector_settings
  drop constraint if exists media_collector_settings_language_filter_mode_check,
  add constraint media_collector_settings_language_filter_mode_check
    check (language_filter_mode in ('prefer', 'strict'));

update public.media_collector_settings
set language_filter_mode = 'strict'
where singleton = true;

comment on column public.media_collector_settings.language_filter_mode is
  'Post-search language policy: prefer ranks matching content first; strict excludes non-matching content except official K-pop channels.';
