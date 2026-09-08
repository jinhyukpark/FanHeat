-- Auditable daily decisions for AI profiles following artists or joining FAN rosters.
-- n8n invokes the AI Worker; only the backend service role can read or write this log.
create table public.ai_artist_engagement_actions (
  id uuid primary key default gen_random_uuid(),
  persona_id uuid not null references public.ai_personas(id) on delete cascade,
  profile_id uuid not null references public.profiles(id) on delete cascade,
  artist_id bigint references public.artists(id) on delete set null,
  action_date date not null default ((now() at time zone 'Asia/Seoul')::date),
  follow_selected boolean not null default false,
  fan_selected boolean not null default false,
  follow_completed boolean not null default false,
  fan_completed boolean not null default false,
  decision_context jsonb not null default '{}'::jsonb,
  status text not null check (status in ('completed', 'skipped', 'failed')),
  error_message text,
  created_at timestamptz not null default now(),
  constraint ai_artist_engagement_action_has_artist check (
    artist_id is not null or (not follow_selected and not fan_selected)
  ),
  unique (persona_id, action_date)
);

create index ai_artist_engagement_actions_artist_date_idx
  on public.ai_artist_engagement_actions (artist_id, action_date desc)
  where artist_id is not null;

alter table public.ai_artist_engagement_actions enable row level security;
revoke all on public.ai_artist_engagement_actions from anon, authenticated;
grant all on public.ai_artist_engagement_actions to service_role;

comment on table public.ai_artist_engagement_actions is
  'Backend-only audit log of once-daily, persona-dependent artist follow and FAN roster decisions invoked by n8n.';
