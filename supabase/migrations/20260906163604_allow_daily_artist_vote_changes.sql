-- Keep one vote per member and day, but allow the selected artist to change
-- until the current Seoul calendar day closes.
grant update (artist_id) on table public.daily_artist_votes to authenticated;

drop policy if exists "Users can change today's vote" on public.daily_artist_votes;
create policy "Users can change today's vote"
on public.daily_artist_votes
for update
to authenticated
using (
  (select auth.uid()) = user_id
  and vote_date = ((now() at time zone 'Asia/Seoul')::date)
)
with check (
  (select auth.uid()) = user_id
  and vote_date = ((now() at time zone 'Asia/Seoul')::date)
);

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

  update public.artist_daily_vote_counts
  set vote_count = greatest(vote_count - 1, 0),
      updated_at = now()
  where artist_id = old.artist_id
    and vote_date = old.vote_date;

  insert into public.artist_daily_vote_counts (artist_id, vote_date, vote_count, updated_at)
  values (new.artist_id, new.vote_date, 1, now())
  on conflict (artist_id, vote_date)
  do update set
    vote_count = public.artist_daily_vote_counts.vote_count + 1,
    updated_at = now();

  return new;
end;
$$;

revoke all on function private.move_artist_daily_vote_count() from public;

drop trigger if exists move_artist_daily_vote_count_after_update on public.daily_artist_votes;
create trigger move_artist_daily_vote_count_after_update
after update of artist_id on public.daily_artist_votes
for each row
execute function private.move_artist_daily_vote_count();
