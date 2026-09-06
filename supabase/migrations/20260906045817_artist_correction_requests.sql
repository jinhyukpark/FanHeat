create table public.artist_correction_requests (
 id uuid primary key,
 artist_id bigint not null references public.artists(id) on delete cascade,
 requester_id uuid not null references auth.users(id),
 category text not null check(category in ('profile','biography','history','awards','albums','gallery','other')),
 message text not null check(length(btrim(message)) between 10 and 5000),
 evidence_url text check(evidence_url is null or evidence_url ~ '^https?://'),
 attachment_paths text[] not null default '{}' check(cardinality(attachment_paths) <= 5),
 status text not null default 'pending' check(status in ('pending','reviewing','resolved','rejected')),
 admin_note text not null default '' check(length(admin_note)<=5000),
 created_at timestamptz not null default now(),
 reviewed_at timestamptz,
 reviewed_by uuid references auth.users(id),
 constraint own_attachment_paths check(attachment_paths <@ array[
 requester_id::text||'/'||id::text||'/1',requester_id::text||'/'||id::text||'/2',
 requester_id::text||'/'||id::text||'/3',requester_id::text||'/'||id::text||'/4',requester_id::text||'/'||id::text||'/5'])
);
create index on public.artist_correction_requests(artist_id,status,created_at desc);
create index on public.artist_correction_requests(requester_id);
alter table public.artist_correction_requests enable row level security;
revoke all on public.artist_correction_requests from anon, authenticated;
grant select,insert on public.artist_correction_requests to authenticated;
grant update(status,admin_note,reviewed_at,reviewed_by) on public.artist_correction_requests to authenticated;
create policy correction_read on public.artist_correction_requests for select to authenticated
 using(requester_id=(select auth.uid()) or (select public.is_admin()));
create policy correction_submit on public.artist_correction_requests for insert to authenticated
 with check(requester_id=(select auth.uid()) and status='pending' and admin_note='' and reviewed_at is null and reviewed_by is null and exists(select 1 from public.artists a where a.id=artist_id and a.active));
create policy correction_review on public.artist_correction_requests for update to authenticated
 using((select public.is_admin())) with check((select public.is_admin()) and reviewed_by=(select auth.uid()));
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
 values('artist-corrections','artist-corrections',false,5242880,array['image/jpeg','image/png','image/webp']);
create policy correction_image_upload on storage.objects for insert to authenticated
 with check(bucket_id='artist-corrections' and (storage.foldername(name))[1]=(select auth.uid())::text
 and name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}/[1-5]$');
create policy correction_image_read on storage.objects for select to authenticated
 using(bucket_id='artist-corrections' and ((storage.foldername(name))[1]=(select auth.uid())::text or (select public.is_admin())));
create policy correction_image_cleanup on storage.objects for delete to authenticated
 using(bucket_id='artist-corrections' and (storage.foldername(name))[1]=(select auth.uid())::text
 and not exists(select 1 from public.artist_correction_requests r where r.id::text=(storage.foldername(name))[2]));
