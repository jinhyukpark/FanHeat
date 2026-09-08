-- AI engagement may support a published member post without an AI source draft
-- or author persona. The post itself remains the unique plan boundary.
alter table public.ai_engagement_plans
  alter column source_draft_id drop not null,
  alter column author_persona_id drop not null;

comment on column public.ai_engagement_plans.source_draft_id is
  'Publishing draft that originated the post; null for member-authored posts.';
comment on column public.ai_engagement_plans.author_persona_id is
  'AI author persona excluded from engagement; null for member-authored posts.';
