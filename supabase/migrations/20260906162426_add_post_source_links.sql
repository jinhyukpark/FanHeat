alter table public.posts
  add column if not exists source_links jsonb not null default '[]'::jsonb;

alter table public.posts
  drop constraint if exists posts_source_links_array,
  add constraint posts_source_links_array
    check (jsonb_typeof(source_links) = 'array' and jsonb_array_length(source_links) <= 10);

update public.posts
set source_links = jsonb_build_array(
  jsonb_strip_nulls(jsonb_build_object('label', source_label, 'url', source_url))
)
where source_url is not null
  and jsonb_array_length(source_links) = 0;

comment on column public.posts.source_links is 'Up to ten optional original-source links shown on the post detail page.';
