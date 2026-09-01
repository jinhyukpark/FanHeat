alter table public.profiles
  add column if not exists avatar_urls text[] not null default '{}'::text[],
  add column if not exists avatar_object_paths text[] not null default '{}'::text[],
  add column if not exists cover_urls text[] not null default '{}'::text[],
  add column if not exists cover_object_paths text[] not null default '{}'::text[];

update public.profiles
set
  avatar_urls = case when coalesce(cardinality(avatar_urls), 0) = 0 and avatar_url is not null then array[avatar_url] else avatar_urls end,
  avatar_object_paths = case when coalesce(cardinality(avatar_object_paths), 0) = 0 and avatar_object_path is not null then array[avatar_object_path] else avatar_object_paths end,
  cover_urls = case when coalesce(cardinality(cover_urls), 0) = 0 and cover_url is not null then array[cover_url] else cover_urls end,
  cover_object_paths = case when coalesce(cardinality(cover_object_paths), 0) = 0 and cover_object_path is not null then array[cover_object_path] else cover_object_paths end;

alter table public.profiles
  drop constraint if exists profiles_avatar_urls_max_five,
  drop constraint if exists profiles_avatar_paths_max_five,
  drop constraint if exists profiles_cover_urls_max_five,
  drop constraint if exists profiles_cover_paths_max_five;

alter table public.profiles
  add constraint profiles_avatar_urls_max_five check (cardinality(avatar_urls) <= 5),
  add constraint profiles_avatar_paths_max_five check (cardinality(avatar_object_paths) <= 5),
  add constraint profiles_cover_urls_max_five check (cardinality(cover_urls) <= 5),
  add constraint profiles_cover_paths_max_five check (cardinality(cover_object_paths) <= 5);

comment on column public.profiles.avatar_urls is 'Up to five ordered profile carousel image URLs';
comment on column public.profiles.cover_urls is 'Up to five ordered profile cover image URLs';
