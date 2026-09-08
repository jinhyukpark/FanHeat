create or replace function private.sync_post_vote_count()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_post_id uuid;
begin
  if tg_op in ('DELETE', 'UPDATE') then
    affected_post_id := old.post_id;

    update public.posts
    set
      vote_count = (
        select count(*)
        from public.post_votes
        where post_id = affected_post_id
      ),
      updated_at = now()
    where id = affected_post_id;
  end if;

  if tg_op = 'INSERT'
    or (tg_op = 'UPDATE' and new.post_id is distinct from old.post_id)
  then
    affected_post_id := new.post_id;

    update public.posts
    set
      vote_count = (
        select count(*)
        from public.post_votes
        where post_id = affected_post_id
      ),
      updated_at = now()
    where id = affected_post_id;
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;

  return new;
end;
$$;

revoke all on function private.sync_post_vote_count() from public, anon, authenticated;

drop trigger if exists post_votes_sync_count on public.post_votes;
create trigger post_votes_sync_count
after insert or delete or update of post_id on public.post_votes
for each row
execute function private.sync_post_vote_count();

-- Restore counters for votes that were already recorded before the trigger existed.
update public.posts as post
set
  vote_count = actual.vote_count,
  updated_at = now()
from (
  select
    candidate.id as post_id,
    count(vote.user_id)::integer as vote_count
  from public.posts as candidate
  left join public.post_votes as vote on vote.post_id = candidate.id
  group by candidate.id
) as actual
where post.id = actual.post_id
  and post.vote_count is distinct from actual.vote_count;

do $$
begin
  if exists (
    select 1
    from public.posts as post
    where post.vote_count is distinct from (
      select count(*)::integer
      from public.post_votes as vote
      where vote.post_id = post.id
    )
  ) then
    raise exception 'post vote counter reconciliation failed';
  end if;
end;
$$;
