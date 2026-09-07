create table if not exists public.post_view_events (
  post_id uuid not null references public.posts(id) on delete cascade,
  viewer_key uuid not null,
  viewed_on date not null default ((now() at time zone 'Asia/Seoul')::date),
  viewed_at timestamptz not null default now(),
  primary key (post_id, viewer_key, viewed_on)
);

create index if not exists post_view_events_period_idx
  on public.post_view_events(viewed_at desc, post_id);

alter table public.post_view_events enable row level security;
revoke all on table public.post_view_events from public, anon, authenticated;

drop function if exists public.record_post_view(uuid);

create or replace function public.record_post_view(p_post_id uuid, p_viewer_key uuid)
returns bigint
language sql
security definer
set search_path = ''
as $$
  with resolved_viewer as (
    select coalesce((select auth.uid()), p_viewer_key) as viewer_key
  ), inserted as (
    insert into public.post_view_events (post_id, viewer_key)
    select posts.id, resolved_viewer.viewer_key
    from public.posts posts
    cross join resolved_viewer
    where posts.id = p_post_id
      and posts.status = 'published'
      and resolved_viewer.viewer_key is not null
    on conflict (post_id, viewer_key, viewed_on) do nothing
    returning post_id
  ), updated as (
    update public.posts posts
    set view_count = coalesce(posts.view_count, 0) + 1
    where posts.id = p_post_id
      and exists (select 1 from inserted)
    returning posts.view_count
  )
  select coalesce(
    (select updated.view_count from updated),
    (select posts.view_count from public.posts posts where posts.id = p_post_id)
  );
$$;

revoke all on function public.record_post_view(uuid, uuid) from public;
grant execute on function public.record_post_view(uuid, uuid) to anon, authenticated;
