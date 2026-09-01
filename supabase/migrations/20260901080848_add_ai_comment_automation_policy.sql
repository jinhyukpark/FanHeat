-- Configuration and auditable reply links for AI comment automation.
-- Browser roles remain unable to access the internal planning tables.

alter table public.media_collector_settings
  add column if not exists ai_comment_min_count smallint not null default 5,
  add column if not exists ai_comment_max_count smallint not null default 30;

alter table public.media_collector_settings
  drop constraint if exists media_collector_settings_ai_comment_count_check,
  add constraint media_collector_settings_ai_comment_count_check
    check (
      ai_comment_min_count between 5 and 30
      and ai_comment_max_count between 5 and 30
      and ai_comment_min_count <= ai_comment_max_count
    );

alter table public.ai_engagement_actions
  add column if not exists parent_action_id uuid
    references public.ai_engagement_actions(id) on delete set null,
  add column if not exists published_comment_id uuid
    references public.comments(id) on delete set null;

alter table public.ai_engagement_actions
  drop constraint if exists ai_engagement_actions_parent_not_self_check,
  add constraint ai_engagement_actions_parent_not_self_check
    check (parent_action_id is null or parent_action_id <> id);

-- Preserve the audit trail while preventing old pending plans from exceeding the new cap.
with ranked_comments as (
  select id, status,
         row_number() over (
           partition by plan_id
           order by scheduled_at, created_at, id
         ) as position
  from public.ai_engagement_actions
  where action_type = 'comment'
)
update public.ai_engagement_actions a
set status = 'skipped',
    error_message = 'comment count capped at 30 by policy',
    executed_at = now(),
    updated_at = now()
from ranked_comments ranked
where a.id = ranked.id and ranked.position > 30 and ranked.status = 'pending';

update public.ai_engagement_plans
set target_comments = least(target_comments, 30),
    updated_at = now()
where target_comments > 30;

alter table public.ai_engagement_plans
  drop constraint if exists ai_engagement_plans_target_comments_check,
  add constraint ai_engagement_plans_target_comments_check
    check (target_comments between 5 and 30);

create index if not exists ai_engagement_actions_parent_action_idx
  on public.ai_engagement_actions(parent_action_id)
  where parent_action_id is not null;

create index if not exists ai_engagement_actions_published_comment_idx
  on public.ai_engagement_actions(published_comment_id)
  where published_comment_id is not null;

comment on column public.media_collector_settings.ai_comment_min_count is
  'Minimum total AI comments, including replies, planned for an eligible AI-authored post';
comment on column public.media_collector_settings.ai_comment_max_count is
  'Maximum total AI comments, including replies, planned for an eligible AI-authored post';
comment on column public.ai_engagement_actions.parent_action_id is
  'Earlier AI comment action whose published comment is the reply target';
comment on column public.ai_engagement_actions.published_comment_id is
  'Comment created by this action, used to resolve later reply actions';
