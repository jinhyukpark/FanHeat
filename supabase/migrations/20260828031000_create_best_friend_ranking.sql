create table if not exists public.friendships (
  owner_id uuid not null references public.profiles(id) on delete cascade,
  friend_id uuid not null references public.profiles(id) on delete cascade,
  status text not null default 'accepted' check (status in ('pending', 'accepted', 'blocked')),
  created_at timestamptz not null default now(),
  accepted_at timestamptz,
  primary key (owner_id, friend_id),
  constraint friendships_not_self check (owner_id <> friend_id)
);

create index if not exists friendships_friend_id_idx on public.friendships(friend_id);
create index if not exists friendships_owner_status_idx on public.friendships(owner_id, status);

alter table public.friendships enable row level security;

drop policy if exists friendships_owner_read on public.friendships;
create policy friendships_owner_read
on public.friendships for select
to authenticated
using ((select auth.uid()) = owner_id);

drop policy if exists friendships_owner_insert on public.friendships;
create policy friendships_owner_insert
on public.friendships for insert
to authenticated
with check ((select auth.uid()) = owner_id);

drop policy if exists friendships_owner_update on public.friendships;
create policy friendships_owner_update
on public.friendships for update
to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists friendships_owner_delete on public.friendships;
create policy friendships_owner_delete
on public.friendships for delete
to authenticated
using ((select auth.uid()) = owner_id);

revoke all on table public.friendships from anon, public;
grant select, insert, update, delete on table public.friendships to authenticated;

create or replace function public.get_my_best_friends()
returns table (
  friend_id uuid,
  display_name text,
  avatar_url text,
  shared_post_count bigint,
  comments_on_my_posts bigint,
  replies_to_my_comments bigint,
  interaction_score bigint,
  last_interaction_at timestamptz,
  star_level integer
)
language sql
stable
security invoker
set search_path = public
as $$
  with me as (
    select (select auth.uid()) as user_id
  ),
  accepted_friends as (
    select f.friend_id
    from public.friendships f, me
    where f.owner_id = me.user_id
      and f.status = 'accepted'
  ),
  shared_posts as (
    select af.friend_id,
           count(distinct friend_comment.post_id)::bigint as event_count,
           max(friend_comment.created_at) as last_at
    from accepted_friends af
    join public.comments friend_comment
      on friend_comment.author_id = af.friend_id
     and friend_comment.deleted_at is null
    where exists (
      select 1
      from public.comments my_comment, me
      where my_comment.post_id = friend_comment.post_id
        and my_comment.author_id = me.user_id
        and my_comment.deleted_at is null
    )
    group by af.friend_id
  ),
  comments_on_posts as (
    select af.friend_id,
           count(*)::bigint as event_count,
           max(friend_comment.created_at) as last_at
    from accepted_friends af
    join public.comments friend_comment
      on friend_comment.author_id = af.friend_id
     and friend_comment.deleted_at is null
    join public.posts my_post on my_post.id = friend_comment.post_id
    join me on my_post.author_id = me.user_id
    group by af.friend_id
  ),
  replies_to_comments as (
    select af.friend_id,
           count(*)::bigint as event_count,
           max(friend_reply.created_at) as last_at
    from accepted_friends af
    join public.comments friend_reply
      on friend_reply.author_id = af.friend_id
     and friend_reply.deleted_at is null
    join public.comments my_comment
      on my_comment.id = friend_reply.parent_id
     and my_comment.deleted_at is null
    join me on my_comment.author_id = me.user_id
    group by af.friend_id
  ),
  scored as (
    select af.friend_id,
           p.display_name,
           p.avatar_url,
           coalesce(sp.event_count, 0)::bigint as shared_post_count,
           coalesce(cp.event_count, 0)::bigint as comments_on_my_posts,
           coalesce(rc.event_count, 0)::bigint as replies_to_my_comments,
           (
             coalesce(sp.event_count, 0) * 4 +
             coalesce(cp.event_count, 0) * 6 +
             coalesce(rc.event_count, 0) * 8
           )::bigint as interaction_score,
           greatest(sp.last_at, cp.last_at, rc.last_at) as last_interaction_at
    from accepted_friends af
    join public.profiles p on p.id = af.friend_id
    left join shared_posts sp on sp.friend_id = af.friend_id
    left join comments_on_posts cp on cp.friend_id = af.friend_id
    left join replies_to_comments rc on rc.friend_id = af.friend_id
  ),
  ranked as (
    select scored.*,
           row_number() over (
             order by interaction_score desc, last_interaction_at desc nulls last, display_name, friend_id
           ) as friend_rank
    from scored
  )
  select ranked.friend_id,
         ranked.display_name,
         ranked.avatar_url,
         ranked.shared_post_count,
         ranked.comments_on_my_posts,
         ranked.replies_to_my_comments,
         ranked.interaction_score,
         ranked.last_interaction_at,
         case when ranked.friend_rank <= 5 then (6 - ranked.friend_rank)::integer else 0 end as star_level
  from ranked
  order by ranked.friend_rank;
$$;

revoke all on function public.get_my_best_friends() from public, anon;
grant execute on function public.get_my_best_friends() to authenticated;

comment on table public.friendships is
  'Owner-scoped FANHEAT friend relationships used for activity-based best-friend ranking.';
comment on function public.get_my_best_friends() is
  'Ranks the signed-in user friends: shared post 4 points, comment on my post 6 points, reply to my comment 8 points; top five receive 5 to 1 stars.';
