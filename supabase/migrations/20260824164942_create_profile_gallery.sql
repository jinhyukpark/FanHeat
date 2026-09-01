create table public.profile_gallery_images (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  object_path text not null unique,
  original_filename text not null,
  mime_type text not null check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
  size_bytes bigint not null check (size_bytes > 0 and size_bytes <= 15728640),
  width integer check (width is null or width > 0),
  height integer check (height is null or height > 0),
  sort_order smallint not null check (sort_order between 0 and 9),
  created_at timestamptz not null default now(),
  unique (user_id, sort_order)
);

create index profile_gallery_images_user_order_idx
  on public.profile_gallery_images (user_id, sort_order);

alter table public.profile_gallery_images enable row level security;

grant select, insert, delete on public.profile_gallery_images to authenticated;
grant usage, select on sequence public.profile_gallery_images_id_seq to authenticated;

create policy "Members can view their gallery"
  on public.profile_gallery_images for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "Members can add to their gallery"
  on public.profile_gallery_images for insert to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Members can delete from their gallery"
  on public.profile_gallery_images for delete to authenticated
  using ((select auth.uid()) = user_id);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'profile-gallery',
  'profile-gallery',
  false,
  15728640,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "Members can upload gallery images"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'profile-gallery'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

create policy "Members can view gallery images"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'profile-gallery'
    and owner_id = (select auth.uid())::text
  );

create policy "Members can delete gallery images"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'profile-gallery'
    and owner_id = (select auth.uid())::text
  );
