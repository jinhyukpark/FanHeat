-- Public-profile projection: accepted friends and display-safe profile fields only.
-- Raw friendship rows, pending/blocked states, bookmarks, and messages remain owner-only.
create or replace function public.get_public_profile_friends(target_user_id uuid)
returns table (id uuid, display_name text, avatar_url text)
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select auth.uid()) is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;
  return query
  select p.id, p.display_name::text, p.avatar_url::text
  from public.friendships f
  join public.profiles p on p.id = f.friend_id
  where f.owner_id = target_user_id and f.status = 'accepted'
  order by f.accepted_at desc nulls last, p.display_name;
end;
$$;

revoke all on function public.get_public_profile_friends(uuid) from public, anon;
grant execute on function public.get_public_profile_friends(uuid) to authenticated;
