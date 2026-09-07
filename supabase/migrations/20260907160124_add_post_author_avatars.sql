alter table public.posts
  add column if not exists author_avatar_url text;

update public.posts as post
set author_avatar_url = profile.avatar_url
from public.profiles as profile
where profile.id = post.author_id
  and nullif(profile.avatar_url, '') is not null
  and post.author_avatar_url is distinct from profile.avatar_url;

create or replace function private.set_post_author_avatar()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if nullif(new.author_avatar_url, '') is null and new.author_id is not null then
    select profile.avatar_url
      into new.author_avatar_url
    from public.profiles as profile
    where profile.id = new.author_id;
  end if;
  return new;
end;
$$;

revoke all on function private.set_post_author_avatar() from public, anon, authenticated;

drop trigger if exists set_post_author_avatar on public.posts;
create trigger set_post_author_avatar
before insert or update of author_id on public.posts
for each row execute function private.set_post_author_avatar();

comment on column public.posts.author_avatar_url is
  'Public author avatar snapshot used by post feeds without exposing profile rows.';
