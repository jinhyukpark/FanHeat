-- FANHEAT Phase 1 external media collector storage.
-- Only the service role may access raw/normalized collector data directly.

create table if not exists public.media_collection_jobs (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('youtube', 'x', 'news')),
  query text not null check (char_length(query) between 1 and 500),
  status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
  cursor text,
  collected_count integer not null default 0 check (collected_count >= 0),
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists media_collection_jobs_source_idx on public.media_collection_jobs (source);
create index if not exists media_collection_jobs_status_idx on public.media_collection_jobs (status);

create table if not exists public.media_raw_items (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('youtube', 'x', 'news')),
  source_content_id text not null,
  payload jsonb not null,
  payload_hash text not null check (char_length(payload_hash) = 64),
  first_collected_at timestamptz not null default now(),
  last_collected_at timestamptz not null default now(),
  constraint media_raw_items_source_content_key unique (source, source_content_id)
);

create index if not exists media_raw_items_source_idx on public.media_raw_items (source);

create table if not exists public.media_items (
  id uuid primary key default gen_random_uuid(),
  raw_item_id uuid references public.media_raw_items(id) on delete set null,
  source text not null check (source in ('youtube', 'x', 'news')),
  source_content_id text not null,
  content_type text not null check (content_type in ('video', 'post', 'article')),
  author jsonb not null default '{}'::jsonb,
  title text,
  text text,
  url text not null,
  thumbnail_url text,
  published_at timestamptz not null,
  entities jsonb not null default '[]'::jsonb,
  enrichment_status text not null default 'pending' check (enrichment_status in ('pending', 'queued', 'completed', 'failed')),
  enrichment jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint media_items_source_content_key unique (source, source_content_id),
  constraint media_items_has_content check (title is not null or text is not null)
);

create index if not exists media_items_source_idx on public.media_items (source);
create index if not exists media_items_published_source_idx on public.media_items (published_at desc, source);
create index if not exists media_items_enrichment_status_idx on public.media_items (enrichment_status);
create index if not exists media_items_entities_gin_idx on public.media_items using gin (entities);

create table if not exists public.media_metric_snapshots (
  id uuid primary key default gen_random_uuid(),
  media_item_id uuid not null references public.media_items(id) on delete cascade,
  views bigint check (views >= 0),
  likes bigint check (likes >= 0),
  comments bigint check (comments >= 0),
  shares bigint check (shares >= 0),
  captured_at timestamptz not null default now()
);

create index if not exists media_metric_snapshots_item_captured_idx
  on public.media_metric_snapshots (media_item_id, captured_at desc);

create table if not exists public.media_collection_rules (
  id uuid primary key default gen_random_uuid(),
  artist_id bigint references public.artists(id) on delete cascade,
  source text not null check (source in ('youtube', 'x', 'news')),
  query text not null check (char_length(query) between 1 and 500),
  interval_seconds integer not null default 600 check (interval_seconds >= 60),
  enabled boolean not null default true,
  last_collected_at timestamptz,
  next_collect_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint media_collection_rules_source_query_artist_key unique nulls not distinct (source, query, artist_id)
);

create index if not exists media_collection_rules_due_idx
  on public.media_collection_rules (next_collect_at) where enabled;

alter table public.media_collection_jobs enable row level security;
alter table public.media_raw_items enable row level security;
alter table public.media_items enable row level security;
alter table public.media_metric_snapshots enable row level security;
alter table public.media_collection_rules enable row level security;

revoke all on public.media_collection_jobs from anon, authenticated;
revoke all on public.media_raw_items from anon, authenticated;
revoke all on public.media_items from anon, authenticated;
revoke all on public.media_metric_snapshots from anon, authenticated;
revoke all on public.media_collection_rules from anon, authenticated;

grant all on public.media_collection_jobs to service_role;
grant all on public.media_raw_items to service_role;
grant all on public.media_items to service_role;
grant all on public.media_metric_snapshots to service_role;
grant all on public.media_collection_rules to service_role;

comment on table public.media_raw_items is 'Immutable-shape upstream payloads; updated only by media-collector service role.';
comment on table public.media_items is 'Cross-platform normalized media content for downstream feed and AI enrichment.';
comment on table public.media_metric_snapshots is 'Time-series engagement metrics used for Heat/Viral score calculation.';
