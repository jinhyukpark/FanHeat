create table public.artist_profile_images (
  id bigint generated always as identity primary key,
  artist_id bigint not null references public.artists(id) on delete cascade,
  image_url text not null check (char_length(image_url) between 8 and 2048),
  display_order integer not null default 0 check (display_order >= 0),
  created_at timestamptz not null default now(),
  unique (artist_id, image_url)
);

insert into public.artist_profile_images (artist_id, image_url, display_order)
select id, image_url, 0 from public.artists where image_url is not null and btrim(image_url) <> ''
on conflict (artist_id, image_url) do nothing;

alter table public.artist_profile_images enable row level security;
create policy artist_profile_images_public_read on public.artist_profile_images
  for select to public using (exists (select 1 from public.artists where artists.id = artist_id and artists.active));
create policy artist_profile_images_admin_all on public.artist_profile_images
  for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
