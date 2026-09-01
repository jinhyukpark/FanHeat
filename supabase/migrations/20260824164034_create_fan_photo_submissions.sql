create table public.fan_photo_submissions (
  id uuid primary key default gen_random_uuid(),
  submitter_id uuid not null references auth.users(id) on delete cascade,
  submitter_name text not null default 'FAN',
  note text,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  admin_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.fan_photo_submission_images (
  id bigint generated always as identity primary key,
  submission_id uuid not null references public.fan_photo_submissions(id) on delete cascade,
  object_path text not null unique,
  original_filename text not null,
  mime_type text not null,
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 26214400),
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  sort_order smallint not null check (sort_order between 0 and 4),
  created_at timestamptz not null default now(),
  unique (submission_id, sort_order)
);

create index fan_photo_submissions_status_created_idx
  on public.fan_photo_submissions(status, created_at desc);
create index fan_photo_submission_images_submission_idx
  on public.fan_photo_submission_images(submission_id, sort_order);

alter table public.fan_photo_submissions enable row level security;
alter table public.fan_photo_submission_images enable row level security;

grant select, insert, delete on public.fan_photo_submissions to authenticated;
grant select, insert on public.fan_photo_submission_images to authenticated;
grant usage, select on sequence public.fan_photo_submission_images_id_seq to authenticated;

create policy fan_photo_submissions_insert_own
on public.fan_photo_submissions for insert to authenticated
with check ((select auth.uid()) = submitter_id);

create policy fan_photo_submissions_select_own
on public.fan_photo_submissions for select to authenticated
using ((select auth.uid()) = submitter_id);

create policy fan_photo_submissions_delete_own
on public.fan_photo_submissions for delete to authenticated
using ((select auth.uid()) = submitter_id and status = 'pending');

create policy fan_photo_submission_images_insert_own
on public.fan_photo_submission_images for insert to authenticated
with check (exists (
  select 1 from public.fan_photo_submissions submission
  where submission.id = submission_id
    and submission.submitter_id = (select auth.uid())
));

create policy fan_photo_submission_images_select_own
on public.fan_photo_submission_images for select to authenticated
using (exists (
  select 1 from public.fan_photo_submissions submission
  where submission.id = submission_id
    and submission.submitter_id = (select auth.uid())
));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'fan-photo-submissions',
  'fan-photo-submissions',
  false,
  26214400,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy fan_photo_storage_insert_own
on storage.objects for insert to authenticated
with check (
  bucket_id = 'fan-photo-submissions'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);

create policy fan_photo_storage_delete_own
on storage.objects for delete to authenticated
using (
  bucket_id = 'fan-photo-submissions'
  and owner_id = (select auth.uid()::text)
);
