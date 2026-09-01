create table public.fan_cred_events (
  id bigint generated always as identity primary key,
  recipient_id uuid not null references auth.users(id) on delete cascade,
  actor_id uuid references auth.users(id) on delete set null,
  source_type text not null check (source_type in ('post_recommendation', 'comment_recommendation', 'post_bookmark', 'verified_information', 'approved_correction', 'valid_report', 'moderation_adjustment')),
  source_key text not null,
  points integer not null check (points between -1000 and 1000 and points <> 0),
  reason text not null,
  created_at timestamptz not null default now(),
  unique (source_type, source_key, actor_id)
);

create index fan_cred_events_recipient_created_idx
  on public.fan_cred_events (recipient_id, created_at desc);

alter table public.fan_cred_events enable row level security;
grant select on public.fan_cred_events to authenticated;

create policy "Members can view their own fan cred"
  on public.fan_cred_events for select to authenticated
  using ((select auth.uid()) = recipient_id);

create or replace function private.sync_post_vote_fan_cred()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_author uuid;
  vote_post_id uuid;
  vote_user_id uuid;
begin
  vote_post_id := coalesce(new.post_id, old.post_id);
  vote_user_id := coalesce(new.user_id, old.user_id);
  select p.author_id into target_author from public.posts p where p.id = vote_post_id;

  if tg_op = 'DELETE' then
    delete from public.fan_cred_events
      where source_type = 'post_recommendation'
        and source_key = vote_post_id::text
        and actor_id = vote_user_id;
    return old;
  end if;

  if target_author is not null and target_author <> vote_user_id then
    insert into public.fan_cred_events (recipient_id, actor_id, source_type, source_key, points, reason)
    values (target_author, vote_user_id, 'post_recommendation', vote_post_id::text, 3, '게시물 추천받음')
    on conflict (source_type, source_key, actor_id) do nothing;
  end if;
  return new;
end;
$$;

revoke execute on function private.sync_post_vote_fan_cred() from public, anon, authenticated;

create trigger post_votes_sync_fan_cred
after insert or delete on public.post_votes
for each row execute function private.sync_post_vote_fan_cred();

create or replace function private.sync_comment_reaction_fan_cred()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_author uuid;
  reaction_comment_id uuid;
  reaction_user_id uuid;
begin
  reaction_comment_id := coalesce(new.comment_id, old.comment_id);
  reaction_user_id := coalesce(new.user_id, old.user_id);
  select c.author_id into target_author from public.comments c where c.id = reaction_comment_id;

  if tg_op in ('DELETE', 'UPDATE') and old.reaction = 'like' then
    delete from public.fan_cred_events
      where source_type = 'comment_recommendation'
        and source_key = reaction_comment_id::text
        and actor_id = reaction_user_id;
  end if;

  if tg_op in ('INSERT', 'UPDATE') and new.reaction = 'like'
     and target_author is not null and target_author <> reaction_user_id then
    insert into public.fan_cred_events (recipient_id, actor_id, source_type, source_key, points, reason)
    values (target_author, reaction_user_id, 'comment_recommendation', reaction_comment_id::text, 1, '댓글 추천받음')
    on conflict (source_type, source_key, actor_id) do nothing;
  end if;
  return coalesce(new, old);
end;
$$;

revoke execute on function private.sync_comment_reaction_fan_cred() from public, anon, authenticated;

create trigger comment_likes_sync_fan_cred
after insert or update or delete on public.comment_likes
for each row execute function private.sync_comment_reaction_fan_cred();

insert into public.fan_cred_events (recipient_id, actor_id, source_type, source_key, points, reason)
select p.author_id, v.user_id, 'post_recommendation', v.post_id::text, 3, '게시물 추천받음'
from public.post_votes v
join public.posts p on p.id = v.post_id
where p.author_id <> v.user_id
on conflict (source_type, source_key, actor_id) do nothing;

insert into public.fan_cred_events (recipient_id, actor_id, source_type, source_key, points, reason)
select c.author_id, l.user_id, 'comment_recommendation', l.comment_id::text, 1, '댓글 추천받음'
from public.comment_likes l
join public.comments c on c.id = l.comment_id
where l.reaction = 'like' and c.author_id <> l.user_id
on conflict (source_type, source_key, actor_id) do nothing;
