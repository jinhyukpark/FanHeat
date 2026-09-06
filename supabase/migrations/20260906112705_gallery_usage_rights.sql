alter table public.artist_gallery_items
  add column if not exists source_provider text,
  add column if not exists creator_name text,
  add column if not exists license_name text,
  add column if not exists license_url text,
  add column if not exists attribution_text text,
  add column if not exists rights_verified_at timestamptz;

comment on column public.artist_gallery_items.source_provider is
  'Source service, such as official_site or wikimedia_commons.';
comment on column public.artist_gallery_items.creator_name is
  'Creator/photographer credit supplied by the source metadata.';
comment on column public.artist_gallery_items.license_name is
  'Human-readable reuse license captured from the source.';
comment on column public.artist_gallery_items.license_url is
  'Canonical license terms URL captured from the source.';
comment on column public.artist_gallery_items.attribution_text is
  'Credit line that must accompany the reused image.';
comment on column public.artist_gallery_items.rights_verified_at is
  'Time the collector verified the structured license metadata.';
