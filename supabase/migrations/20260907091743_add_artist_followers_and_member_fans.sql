-- User-controlled artist following is separate from joining an artist's FAN roster.
create table if not exists public.artist_followers (
  artist_id bigint not null references public.artists(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (artist_id, user_id)
);

alter table public.artist_followers enable row level security;
grant select, insert, delete on public.artist_followers to authenticated;

create policy artist_followers_own_read on public.artist_followers
  for select to authenticated using ((select auth.uid()) = user_id);
create policy artist_followers_own_insert on public.artist_followers
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy artist_followers_own_delete on public.artist_followers
  for delete to authenticated using ((select auth.uid()) = user_id);

create or replace function private.sync_artist_follower_count()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  target_artist_id bigint := coalesce(new.artist_id, old.artist_id);
begin
  update public.artists
  set follower_count = greatest(0, follower_count + case when tg_op = 'INSERT' then 1 else -1 end),
      updated_at = now()
  where id = target_artist_id;
  return coalesce(new, old);
end;
$$;
revoke all on function private.sync_artist_follower_count() from public, anon, authenticated;

drop trigger if exists sync_artist_follower_count on public.artist_followers;
create trigger sync_artist_follower_count
after insert or delete on public.artist_followers
for each row execute function private.sync_artist_follower_count();

-- One authenticated profile can join each artist FAN roster once.
create unique index if not exists artist_fans_artist_profile_unique
  on public.artist_fans(artist_id, profile_id);

drop policy if exists artist_fans_visible_read on public.artist_fans;
drop policy if exists artist_fans_admin_insert on public.artist_fans;
drop policy if exists artist_fans_admin_update on public.artist_fans;
drop policy if exists artist_fans_admin_delete on public.artist_fans;

create policy artist_fans_visible_read on public.artist_fans
  for select to public using (active or (select public.is_admin()));
create policy artist_fans_member_or_admin_insert on public.artist_fans
  for insert to authenticated with check (
    (select public.is_admin()) or (select auth.uid()) = profile_id
  );
create policy artist_fans_member_or_admin_update on public.artist_fans
  for update to authenticated
  using ((select public.is_admin()) or (select auth.uid()) = profile_id)
  with check ((select public.is_admin()) or (select auth.uid()) = profile_id);
create policy artist_fans_member_or_admin_delete on public.artist_fans
  for delete to authenticated using (
    (select public.is_admin()) or (select auth.uid()) = profile_id
  );
