alter table public.profiles
  add column if not exists cover_url text,
  add column if not exists avatar_object_path text,
  add column if not exists cover_object_path text,
  add column if not exists profile_headline text,
  add column if not exists facebook_url text,
  add column if not exists x_url text,
  add column if not exists instagram_url text,
  add column if not exists tiktok_url text,
  add column if not exists youtube_url text,
  add column if not exists favorite_track_id bigint references public.tracks(id) on delete set null;

comment on column public.profiles.profile_headline is
  'Short message displayed over the profile cover image';

comment on column public.profiles.favorite_track_id is
  'Track selected as the member profile theme song';
