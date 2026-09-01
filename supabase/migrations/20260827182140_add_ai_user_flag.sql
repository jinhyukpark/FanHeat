-- AI-operated fans remain normal authenticated users so their posts and
-- comments keep the existing author foreign keys. This profile flag is the
-- canonical way to distinguish them from human-operated accounts.
alter table public.profiles
  add column if not exists is_ai boolean not null default false;

comment on column public.profiles.is_ai is
  'True when this fan account is operated by FANHEAT automation rather than a human';

create index if not exists profiles_ai_users_idx
  on public.profiles (id)
  where is_ai;

-- Profile owners can update their own rows under the existing RLS policy, but
-- only administrators or trusted backend/database roles may change identity.
create or replace function public.protect_profile_ai_flag()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.is_ai is distinct from coalesce(old.is_ai, false)
     and not public.is_admin()
     and current_user not in ('service_role', 'postgres', 'supabase_admin') then
    raise exception 'Only administrators may change profiles.is_ai'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke all on function public.protect_profile_ai_flag() from public, anon, authenticated;

drop trigger if exists protect_profile_ai_flag on public.profiles;
create trigger protect_profile_ai_flag
before insert or update of is_ai on public.profiles
for each row execute function public.protect_profile_ai_flag();
