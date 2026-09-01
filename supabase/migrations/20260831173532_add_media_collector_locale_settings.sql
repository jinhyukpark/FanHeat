-- Internal locale preferences shared by the collector admin and n8n jobs.
create table if not exists public.media_collector_settings (
  singleton boolean primary key default true check (singleton),
  region_code varchar(2) not null default 'KR' check (region_code ~ '^[A-Z]{2}$'),
  language_code varchar(10) not null default 'ko' check (language_code ~ '^[A-Za-z]{2,3}(-[A-Za-z]{2,8})?$'),
  updated_at timestamptz not null default now()
);

insert into public.media_collector_settings (singleton, region_code, language_code)
values (true, 'KR', 'ko')
on conflict (singleton) do nothing;

alter table public.media_collector_settings enable row level security;
revoke all on public.media_collector_settings from anon, authenticated;
grant all on public.media_collector_settings to service_role;

comment on table public.media_collector_settings is
  'Internal collector locale settings. Browser roles have no direct access; collector and n8n use server-side APIs.';
