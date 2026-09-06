-- Treat daily_artist_votes as the source of truth. A changed vote must move the
-- member's single daily vote instead of leaving the old aggregate behind.
create or replace function private.move_artist_daily_vote_count()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.artist_id = old.artist_id then
    return new;
  end if;

  insert into public.artist_daily_vote_counts (artist_id, vote_date, vote_count, updated_at)
  values (
    old.artist_id,
    old.vote_date,
    (
      select count(*)::integer
      from public.daily_artist_votes
      where artist_id = old.artist_id
        and vote_date = old.vote_date
    ),
    now()
  )
  on conflict (artist_id, vote_date)
  do update set
    vote_count = excluded.vote_count,
    updated_at = excluded.updated_at;

  insert into public.artist_daily_vote_counts (artist_id, vote_date, vote_count, updated_at)
  values (
    new.artist_id,
    new.vote_date,
    (
      select count(*)::integer
      from public.daily_artist_votes
      where artist_id = new.artist_id
        and vote_date = new.vote_date
    ),
    now()
  )
  on conflict (artist_id, vote_date)
  do update set
    vote_count = excluded.vote_count,
    updated_at = excluded.updated_at;

  return new;
end;
$$;

revoke all on function private.move_artist_daily_vote_count() from public;

drop trigger if exists move_artist_daily_vote_count_after_update on public.daily_artist_votes;
create trigger move_artist_daily_vote_count_after_update
after update of artist_id on public.daily_artist_votes
for each row
execute function private.move_artist_daily_vote_count();

-- Repair any counts that were already left behind by an earlier vote change.
insert into public.artist_daily_vote_counts (artist_id, vote_date, vote_count, updated_at)
select artist_id, vote_date, count(*)::integer, now()
from public.daily_artist_votes
group by artist_id, vote_date
on conflict (artist_id, vote_date)
do update set
  vote_count = excluded.vote_count,
  updated_at = excluded.updated_at;

update public.artist_daily_vote_counts counts
set vote_count = 0,
    updated_at = now()
where not exists (
  select 1
  from public.daily_artist_votes votes
  where votes.artist_id = counts.artist_id
    and votes.vote_date = counts.vote_date
);
