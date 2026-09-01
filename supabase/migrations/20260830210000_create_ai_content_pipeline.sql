-- FANHEAT local-LLM personas and review-first content pipeline.
-- These tables are backend-only. AI drafts must be reviewed before publication.

create table if not exists public.ai_personas (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid unique references public.profiles(id) on delete set null,
  display_name text not null unique check (char_length(display_name) between 1 and 80),
  role text not null check (char_length(role) between 1 and 80),
  tone text not null default '친근하고 정확한 한국어',
  system_prompt text not null default '',
  interests jsonb not null default '[]'::jsonb check (jsonb_typeof(interests) = 'array'),
  prohibited_topics jsonb not null default '[]'::jsonb check (jsonb_typeof(prohibited_topics) = 'array'),
  daily_post_limit integer not null default 3 check (daily_post_limit between 0 and 20),
  daily_comment_limit integer not null default 8 check (daily_comment_limit between 0 and 50),
  active_hours int4range not null default int4range(8, 24, '[)'),
  model_name text,
  enabled boolean not null default true,
  last_used_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ai_content_drafts (
  id uuid primary key default gen_random_uuid(),
  persona_id uuid not null references public.ai_personas(id) on delete restrict,
  content_type text not null check (content_type in ('post', 'comment')),
  generation_key text not null unique,
  source_media_item_ids uuid[] not null default '{}',
  parent_post_id uuid references public.posts(id) on delete cascade,
  parent_comment_id uuid references public.comments(id) on delete set null,
  title text,
  body text not null check (char_length(body) between 1 and 5000),
  tags jsonb not null default '[]'::jsonb check (jsonb_typeof(tags) = 'array'),
  model_name text not null,
  prompt_version text not null,
  status text not null default 'generated'
    check (status in ('generated', 'review', 'approved', 'scheduled', 'published', 'rejected', 'failed')),
  risk_flags jsonb not null default '[]'::jsonb check (jsonb_typeof(risk_flags) = 'array'),
  confidence numeric(4, 3) check (confidence between 0 and 1),
  scheduled_at timestamptz,
  published_post_id uuid references public.posts(id) on delete set null,
  published_comment_id uuid references public.comments(id) on delete set null,
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  rejection_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ai_content_drafts_post_title check (content_type <> 'post' or title is not null),
  constraint ai_content_drafts_comment_parent check (content_type <> 'comment' or parent_post_id is not null)
);

create table if not exists public.ai_pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  trigger_source text not null default 'n8n',
  status text not null check (status in ('running', 'completed', 'partial', 'failed')),
  processed_count integer not null default 0 check (processed_count >= 0),
  draft_count integer not null default 0 check (draft_count >= 0),
  failed_count integer not null default 0 check (failed_count >= 0),
  error_message text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists ai_personas_enabled_used_idx
  on public.ai_personas (last_used_at nulls first) where enabled;
create index if not exists ai_content_drafts_status_schedule_idx
  on public.ai_content_drafts (status, scheduled_at, created_at desc);
create index if not exists ai_content_drafts_persona_created_idx
  on public.ai_content_drafts (persona_id, created_at desc);
create index if not exists ai_content_drafts_source_items_gin_idx
  on public.ai_content_drafts using gin (source_media_item_ids);

alter table public.ai_personas enable row level security;
alter table public.ai_content_drafts enable row level security;
alter table public.ai_pipeline_runs enable row level security;

revoke all on public.ai_personas from anon, authenticated;
revoke all on public.ai_content_drafts from anon, authenticated;
revoke all on public.ai_pipeline_runs from anon, authenticated;
grant all on public.ai_personas to service_role;
grant all on public.ai_content_drafts to service_role;
grant all on public.ai_pipeline_runs to service_role;

insert into public.ai_personas (display_name, role, tone, system_prompt, interests)
values
  ('FANHEAT 뉴스봇', '공식 소식 전달', '간결하고 정확한 존댓말', '공식 발표와 확인된 일정만 전달한다.', '["공식 발표", "발매", "공연"]'),
  ('FANHEAT 데이터팬', '지표와 반응 분석', '숫자를 쉽게 설명하는 존댓말', '수집된 지표에 없는 수치를 추정하지 않는다.', '["조회수", "차트", "반응 추이"]'),
  ('FANHEAT 응원팬', '건강한 응원과 축하', '따뜻하지만 과장하지 않는 말투', '다른 아티스트나 팬덤을 비교하거나 비하하지 않는다.', '["응원", "축하"]'),
  ('FANHEAT 토론팬', '정보 기반 질문', '열린 질문을 사용하는 중립적 말투', '갈등이나 과도한 참여를 유도하지 않는다.', '["감상", "질문"]'),
  ('FANHEAT 글로벌팬', '해외 공식 반응 요약', '자연스러운 한국어 요약체', '원문의 맥락과 출처를 유지한다.', '["해외 뉴스", "글로벌 반응"]')
on conflict do nothing;

comment on table public.ai_personas is 'Disclosed AI-operated FANHEAT account personas. profile_id is linked after account provisioning.';
comment on table public.ai_content_drafts is 'Review-first LLM output with provenance; never exposed directly to clients.';
