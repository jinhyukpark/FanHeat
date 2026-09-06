alter table public.artist_gallery_items
  add column if not exists source_page_url text,
  add column if not exists original_image_url text,
  add column if not exists source_collected_at timestamptz;
comment on column public.artist_gallery_items.source_page_url is 'Page where this image was actually discovered; NULL when unknown.';
comment on column public.artist_gallery_items.original_image_url is 'Original remote image URL, separate from stored/display image URL.';
comment on column public.artist_gallery_items.source_collected_at is 'Time provenance was captured by the collector; not a publication date.';
