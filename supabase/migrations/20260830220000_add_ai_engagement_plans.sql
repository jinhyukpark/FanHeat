-- Per-post engagement plans for disclosed AI personas.
-- Backend-only: plans and queued actions are never exposed to public clients.

create table if not exists public.ai_engagement_plans (
  id uuid primary key default gen_random_uuid(),
  post_id uuid not null unique references public.posts(id) on delete cascade,
  source_draft_id uuid not null unique references public.ai_content_drafts(id) on delete cascade,
  author_persona_id uuid not null references public.ai_personas(id) on delete restrict,
  status text not null default 'active'
    check (status in ('active', 'completed', 'cancelled', 'failed')),
  engagement_score numeric(5, 4) not null check (engagement_score between 0 and 1),
  target_comments integer not null check (target_comments between 5 and 50),
  target_post_heats integer not null default 0 check (target_post_heats between 0 and 50),
  target_comment_likes integer not null default 0 check (target_comment_likes between 0 and 50),
  starts_at timestamptz not null,
  ends_at timestamptz not null check (ends_at > starts_at),
  rationale jsonb not null default '{}'::jsonb check (jsonb_typeof(rationale) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ai_engagement_actions (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.ai_engagement_plans(id) on delete cascade,
  persona_id uuid not null references public.ai_personas(id) on delete restrict,
  action_type text not null check (action_type in ('comment', 'post_heat', 'comment_like')),
  target_comment_id uuid references public.comments(id) on delete cascade,
  draft_id uuid references public.ai_content_drafts(id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'skipped', 'failed')),
  scheduled_at timestamptz not null,
  executed_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ai_engagement_plans_status_ends_idx
  on public.ai_engagement_plans (status, ends_at);
create index if not exists ai_engagement_actions_due_idx
  on public.ai_engagement_actions (status, scheduled_at) where status = 'pending';
create unique index if not exists ai_engagement_actions_one_post_heat_per_persona
  on public.ai_engagement_actions (plan_id, persona_id)
  where action_type = 'post_heat';

alter table public.ai_engagement_plans enable row level security;
alter table public.ai_engagement_actions enable row level security;

revoke all on public.ai_engagement_plans from anon, authenticated;
revoke all on public.ai_engagement_actions from anon, authenticated;
grant all on public.ai_engagement_plans to service_role;
grant all on public.ai_engagement_actions to service_role;

comment on table public.ai_engagement_plans is
  'Backend-only comment, HEAT, and comment-like targets for disclosed AI personas.';
comment on table public.ai_engagement_actions is
  'Scheduled, auditable AI engagement actions. A five-minute runner executes only due rows.';
