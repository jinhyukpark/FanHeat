alter table public.ai_content_drafts
  add column if not exists trigger_source text not null default 'manual';

comment on column public.ai_content_drafts.trigger_source is
  'Origin of draft generation. Only admin_full_automation is eligible for policy-driven scheduled publishing.';

create index if not exists ai_content_drafts_automation_publish_idx
  on public.ai_content_drafts (status, scheduled_at, created_at)
  where approval_source = 'auto_policy' and trigger_source = 'admin_full_automation';
