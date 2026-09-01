-- Keep user-uploadable public assets browser-safe. SVG can execute active content
-- when opened directly, so it is intentionally excluded from this public bucket.
update storage.buckets
set allowed_mime_types = array[
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif'
]::text[]
where id = 'fanheat-assets';

-- Cover foreign keys used during deletes and relationship lookups.
create index if not exists artist_fans_profile_id_idx
  on public.artist_fans(profile_id)
  where profile_id is not null;

create index if not exists private_messages_reply_to_id_idx
  on public.private_messages(reply_to_id)
  where reply_to_id is not null;

create index if not exists profiles_favorite_track_id_idx
  on public.profiles(favorite_track_id)
  where favorite_track_id is not null;
