-- Optional, clickable provenance for a post and for each featured image.
-- Existing reference_url remains the primary embedded-media URL for backwards
-- compatibility; source_url is dedicated to attribution.
alter table public.posts
  add column if not exists source_label text,
  add column if not exists source_url text,
  add column if not exists inline_image_sources jsonb not null default '[]'::jsonb;

alter table public.post_images
  add column if not exists source_label text,
  add column if not exists source_url text;

alter table public.posts
  drop constraint if exists posts_source_label_length,
  add constraint posts_source_label_length
    check (source_label is null or char_length(source_label) <= 120),
  drop constraint if exists posts_source_url_http,
  add constraint posts_source_url_http
    check (source_url is null or (char_length(source_url) <= 2048 and source_url ~* '^https?://')),
  drop constraint if exists posts_inline_image_sources_array,
  add constraint posts_inline_image_sources_array
    check (jsonb_typeof(inline_image_sources) = 'array');

alter table public.post_images
  drop constraint if exists post_images_source_label_length,
  add constraint post_images_source_label_length
    check (source_label is null or char_length(source_label) <= 120),
  drop constraint if exists post_images_source_url_http,
  add constraint post_images_source_url_http
    check (source_url is null or (char_length(source_url) <= 2048 and source_url ~* '^https?://'));

comment on column public.posts.source_label is 'Optional publisher or source name displayed with the post attribution link.';
comment on column public.posts.source_url is 'Optional HTTP(S) page used as the post source attribution.';
comment on column public.posts.inline_image_sources is 'Optional per-image attribution for images embedded in body_html.';
comment on column public.post_images.source_label is 'Optional creator, publisher, or source name for this featured image.';
comment on column public.post_images.source_url is 'Optional HTTP(S) page containing provenance for this featured image.';
