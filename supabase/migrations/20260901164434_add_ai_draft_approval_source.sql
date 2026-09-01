alter table public.ai_content_drafts
  add column if not exists approval_source text;

alter table public.ai_content_drafts
  add constraint ai_content_drafts_approval_source_check
  check (approval_source is null or approval_source in ('admin_manual', 'admin_bulk', 'n8n', 'auto_policy'));

-- Before this migration, only an explicit review action populated reviewed_at.
update public.ai_content_drafts
set approval_source = 'admin_manual'
where approval_source is null and reviewed_at is not null;

comment on column public.ai_content_drafts.approval_source is
  'Approval provenance: admin_manual, admin_bulk, n8n, or auto_policy. Null means legacy/unrecorded.';
