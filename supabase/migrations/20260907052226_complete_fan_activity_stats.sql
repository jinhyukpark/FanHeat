-- Scores are derived from trusted activity rows, never editable profile metadata.
create schema if not exists private;
create table private.heat_activity_events (
  user_id uuid not null references auth.users(id) on delete cascade,
  source_type text not null,
  source_key text not null,
  points integer not null check (points > 0 and points <= 100),
  occurred_at timestamptz not null,
  active boolean not null default true,
  primary key (user_id, source_type, source_key)
);
alter table private.heat_activity_events enable row level security;
revoke all on private.heat_activity_events from public, anon, authenticated;
create index heat_activity_replay on private.heat_activity_events(user_id, occurred_at) where active;

create function private.record_heat_activity(t text, r jsonb, removed boolean, event_time timestamptz)
returns void language plpgsql security definer set search_path = '' as $$
declare
  uid uuid; kind text; key text; weight integer; enabled boolean := not removed;
  other uuid; pair text;
begin
  if t = 'friendships' then
    uid := (r->>'owner_id')::uuid; other := (r->>'friend_id')::uuid;
    if uid = other then return; end if;
    pair := least(uid::text, other::text) || ':' || greatest(uid::text, other::text);
    enabled := exists(select 1 from public.friendships f where
      ((f.owner_id=uid and f.friend_id=other) or (f.owner_id=other and f.friend_id=uid))
      and f.status='accepted');
    if not enabled then
      update private.heat_activity_events set active=false where source_type='friendship' and source_key=pair;
      return;
    end if;
    insert into private.heat_activity_events(user_id,source_type,source_key,points,occurred_at,active)
    values(uid,'friendship',pair,12,event_time,enabled),(other,'friendship',pair,12,event_time,enabled)
    on conflict(user_id,source_type,source_key) do update set active=excluded.active;
    return;
  elsif t = 'posts' then
    uid := (r->>'author_id')::uuid; kind := 'post'; key := r->>'id'; weight := 18;
    enabled := enabled and r->>'status' = 'published';
  elsif t = 'comments' then
    uid := (r->>'author_id')::uuid; kind := 'comment'; key := r->>'id'; weight := 6;
    enabled := enabled and (r->>'deleted_at') is null;
  elsif t = 'profile_gallery_images' then
    uid := (r->>'user_id')::uuid; kind := 'gallery'; key := r->>'object_path'; weight := 4;
  elsif t = 'post_bookmarks' then
    uid := (r->>'user_id')::uuid; kind := 'bookmark'; key := r->>'post_id'; weight := 3;
  elsif t = 'post_votes' then
    uid := (r->>'user_id')::uuid; kind := 'post_vote'; key := r->>'post_id'; weight := 2;
  elsif t = 'daily_artist_votes' then
    uid := (r->>'user_id')::uuid; kind := 'daily_vote'; key := r->>'vote_date'; weight := 2;
  else return;
  end if;
  if uid is null or key is null then return; end if;
  -- Do not record drafts/pending events until their first eligible transition.
  if enabled then
    insert into private.heat_activity_events(user_id,source_type,source_key,points,occurred_at,active)
    values(uid,kind,key,weight,event_time,true)
    on conflict(user_id,source_type,source_key) do update set active=true;
  else
    update private.heat_activity_events set active=false
      where user_id=uid and source_type=kind and source_key=key;
  end if;
end $$;
revoke all on function private.record_heat_activity(text,jsonb,boolean,timestamptz) from public,anon,authenticated;

create function private.sync_heat_activity()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if TG_OP <> 'INSERT' then
    perform private.record_heat_activity(TG_TABLE_NAME,to_jsonb(old),true,statement_timestamp());
  end if;
  if TG_OP <> 'DELETE' then
    perform private.record_heat_activity(TG_TABLE_NAME,to_jsonb(new),false,statement_timestamp());
  end if;
  return null;
end $$;
revoke all on function private.sync_heat_activity() from public,anon,authenticated;

do $$
declare t text; r jsonb;
begin
  foreach t in array array['posts','comments','profile_gallery_images','post_bookmarks','post_votes','daily_artist_votes','friendships'] loop
    execute format('create trigger sync_heat_activity after insert or update or delete on public.%I for each row execute function private.sync_heat_activity()',t);
    for r in execute format('select to_jsonb(s) from public.%I s',t) loop
      perform private.record_heat_activity(t,r,false,coalesce((r->>'accepted_at')::timestamptz,(r->>'created_at')::timestamptz,now()));
    end loop;
  end loop;
end $$;

-- Private replay also accepts a clock for deterministic tests; clients cannot call it.
create function private.heat_snapshot(target uuid, at_time timestamptz)
returns jsonb language plpgsql stable set search_path = '' as $$
declare e record; heat numeric := 0; before_heat numeric; maximums integer := 0;
  last_at timestamptz; ttl integer := 0;
begin
  for e in select * from private.heat_activity_events
    where user_id=target and active and occurred_at<=at_time
    order by occurred_at,source_type,source_key
  loop
    if last_at is not null then
      heat := round(heat * greatest(0,1-extract(epoch from (e.occurred_at-last_at))/2592000));
    end if;
    before_heat := heat;
    heat := least(100,heat+e.points);
    if before_heat<100 and heat=100 then maximums := maximums+1; end if;
    last_at := e.occurred_at;
  end loop;
  if last_at is not null then
    heat := round(heat * greatest(0,1-extract(epoch from (at_time-last_at))/2592000));
    if heat>0 then ttl := greatest(0,ceil(30-extract(epoch from (at_time-last_at))/86400)); end if;
  end if;
  return jsonb_build_object('heat_range',heat,'heat_max_count',maximums,
    'heat_days_remaining',ttl,'last_heat_activity_at',last_at);
end $$;
revoke all on function private.heat_snapshot(uuid,timestamptz) from public,anon,authenticated;

-- Exposes only public profile aggregates, not actors or their activity histories.
create function private.get_fan_stats(target uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare result jsonb; credit bigint := 0; position bigint := 0; members bigint := 0;
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  if not exists(select 1 from public.profiles where id=target) then
    raise exception 'Profile not found' using errcode='P0002';
  end if;
  result := private.heat_snapshot(target,statement_timestamp());
  select greatest(0,coalesce(sum(points),0)) into credit from public.fan_cred_events where recipient_id=target;
  with scores as (
    select recipient_id, sum(points) as score from public.fan_cred_events
    group by recipient_id having sum(points)>0
  )
  select count(*),case when credit>0 then 1+count(*) filter(where score>credit) else 0 end
    into members,position from scores;
  return result || jsonb_build_object('fan_credit',credit,'fan_rank',position,'fan_rank_total',members);
end $$;
revoke all on function private.get_fan_stats(uuid) from public,anon,authenticated;
grant usage on schema private to authenticated;
grant execute on function private.get_fan_stats(uuid) to authenticated;
create function public.get_fan_stats(target uuid)
returns jsonb language sql stable security invoker set search_path = ''
as $$ select private.get_fan_stats(target) $$;
revoke all on function public.get_fan_stats(uuid) from public,anon;
grant execute on function public.get_fan_stats(uuid) to authenticated;
