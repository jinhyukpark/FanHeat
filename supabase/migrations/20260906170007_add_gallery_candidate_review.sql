alter table public.artist_gallery_items
  add column if not exists ai_decision text
    check (ai_decision is null or ai_decision in ('photo_candidate', 'review', 'exclude')),
  add column if not exists ai_reason text,
  add column if not exists ai_confidence numeric
    check (ai_confidence is null or (ai_confidence >= 0 and ai_confidence <= 1)),
  add column if not exists ai_category text,
  add column if not exists ai_people_visible boolean,
  add column if not exists ai_promotional_layout boolean,
  add column if not exists review_status text
    check (review_status is null or review_status in ('pending', 'approved', 'rejected')),
  add column if not exists reviewed_at timestamptz;

comment on column public.artist_gallery_items.ai_decision is
  'Latest collector vision verdict. Human review_status remains authoritative.';
comment on column public.artist_gallery_items.ai_reason is
  'Reason returned by the gallery vision classifier.';
comment on column public.artist_gallery_items.review_status is
  'Super-administrator decision for a collected image candidate.';
comment on column public.artist_gallery_items.reviewed_at is
  'Time the collected candidate was approved or rejected by an administrator.';

create index if not exists artist_gallery_pending_review_idx
  on public.artist_gallery_items(artist_id, created_at desc)
  where review_status = 'pending';

-- Preserve the latest classifier result already stored in completed collector
-- reports so administrators do not have to run the expensive vision job again.
with latest_candidates as (
  select distinct on ((job.cursor::jsonb->>'artist_id')::bigint, candidate.item->>'image_url')
    (job.cursor::jsonb->>'artist_id')::bigint as artist_id,
    candidate.item,
    coalesce(job.completed_at, job.updated_at, job.created_at) as classified_at
  from public.media_collection_jobs job
  cross join lateral jsonb_array_elements(
    coalesce(job.cursor::jsonb #> '{report,gallery_review,items}', '[]'::jsonb)
  ) as candidate(item)
  where job.source = 'artist'
    and job.cursor is not null
    and job.cursor::jsonb->>'artist_id' ~ '^[0-9]+$'
    and candidate.item->>'image_url' ~ '^https?://'
  order by (job.cursor::jsonb->>'artist_id')::bigint,
           candidate.item->>'image_url',
           coalesce(job.completed_at, job.updated_at, job.created_at) desc
)
update public.artist_gallery_items gallery
set ai_decision = latest.item->>'decision',
    ai_reason = nullif(latest.item->>'reason', ''),
    ai_confidence = case when latest.item->>'confidence' ~ '^(0(\.\d+)?|1(\.0+)?)$'
      then (latest.item->>'confidence')::numeric else null end,
    ai_category = nullif(latest.item->>'category', ''),
    ai_people_visible = case when latest.item->>'people_visible' in ('true', 'false')
      then (latest.item->>'people_visible')::boolean else null end,
    ai_promotional_layout = case when latest.item->>'promotional_layout' in ('true', 'false')
      then (latest.item->>'promotional_layout')::boolean else null end,
    review_status = case when gallery.active then 'approved' else coalesce(gallery.review_status, 'pending') end,
    reviewed_at = case when gallery.active then coalesce(gallery.reviewed_at, gallery.updated_at) else gallery.reviewed_at end,
    updated_at = now()
from latest_candidates latest
where gallery.artist_id = latest.artist_id
  and gallery.image_url = latest.item->>'image_url';

with latest_candidates as (
  select distinct on ((job.cursor::jsonb->>'artist_id')::bigint, candidate.item->>'image_url')
    (job.cursor::jsonb->>'artist_id')::bigint as artist_id,
    candidate.item,
    coalesce(job.completed_at, job.updated_at, job.created_at) as classified_at
  from public.media_collection_jobs job
  cross join lateral jsonb_array_elements(
    coalesce(job.cursor::jsonb #> '{report,gallery_review,items}', '[]'::jsonb)
  ) as candidate(item)
  where job.source = 'artist'
    and job.cursor is not null
    and job.cursor::jsonb->>'artist_id' ~ '^[0-9]+$'
    and candidate.item->>'image_url' ~ '^https?://'
  order by (job.cursor::jsonb->>'artist_id')::bigint,
           candidate.item->>'image_url',
           coalesce(job.completed_at, job.updated_at, job.created_at) desc
)
insert into public.artist_gallery_items (
  artist_id, title, image_url, active, display_order,
  source_page_url, original_image_url, source_collected_at, source_provider,
  creator_name, license_name, license_url, attribution_text, rights_verified_at,
  ai_decision, ai_reason, ai_confidence, ai_category, ai_people_visible,
  ai_promotional_layout, review_status
)
select latest.artist_id,
  case latest.item->>'decision'
    when 'photo_candidate' then 'AI 활동 사진 후보 · 확인 필요'
    when 'review' then 'AI 판별 보류 이미지 · 확인 필요'
    else 'AI 제외 권고 이미지 · 확인 필요'
  end,
  latest.item->>'image_url', false, 0,
  nullif(latest.item->>'source_url', ''),
  coalesce(nullif(latest.item->>'original_image_url', ''), latest.item->>'image_url'),
  coalesce(nullif(latest.item->>'source_collected_at', '')::timestamptz, latest.classified_at),
  nullif(latest.item->>'source_provider', ''),
  nullif(latest.item->>'creator_name', ''),
  nullif(latest.item->>'license_name', ''),
  nullif(latest.item->>'license_url', ''),
  nullif(latest.item->>'attribution_text', ''),
  case when nullif(latest.item->>'license_name', '') is not null then latest.classified_at else null end,
  latest.item->>'decision',
  nullif(latest.item->>'reason', ''),
  case when latest.item->>'confidence' ~ '^(0(\.\d+)?|1(\.0+)?)$'
    then (latest.item->>'confidence')::numeric else null end,
  nullif(latest.item->>'category', ''),
  case when latest.item->>'people_visible' in ('true', 'false')
    then (latest.item->>'people_visible')::boolean else null end,
  case when latest.item->>'promotional_layout' in ('true', 'false')
    then (latest.item->>'promotional_layout')::boolean else null end,
  'pending'
from latest_candidates latest
where exists (select 1 from public.artists artist where artist.id = latest.artist_id)
  and not exists (
    select 1 from public.artist_gallery_items gallery
    where gallery.artist_id = latest.artist_id
      and gallery.image_url = latest.item->>'image_url'
  );
