-- Local fixture only; all test rows roll back.
begin;
insert into auth.users values ('00000000-0000-4000-8000-000000000001'),('00000000-0000-4000-8000-000000000002'),('00000000-0000-4000-8000-000000000003');
insert into public.profiles select id from auth.users;
select set_config('request.jwt.claim.sub','00000000-0000-4000-8000-000000000001',true);
do $$
declare
  a uuid := '00000000-0000-4000-8000-000000000001';
  b uuid := '00000000-0000-4000-8000-000000000002';
  c uuid := '00000000-0000-4000-8000-000000000003';
  p uuid := '10000000-0000-4000-8000-000000000001';
  r jsonb; original_time timestamptz;
begin
  r := public.get_fan_stats(a);
  assert (r->>'heat_range')::int=0 and (r->>'heat_days_remaining')::int=0 and (r->>'fan_credit')::int=0;
  insert into public.posts values(p,a,'draft',now());
  assert (public.get_fan_stats(a)->>'heat_range')::int=0;
  update public.posts set status='published' where id=p;
  assert (public.get_fan_stats(a)->>'heat_range')::int=18;
  update public.posts set status='published' where id=p;
  assert (public.get_fan_stats(a)->>'heat_range')::int=18;
  insert into public.post_votes(user_id,post_id) values(b,p);
  assert (public.get_fan_stats(a)->>'fan_credit')::int=3;
  assert (public.get_fan_stats(b)->>'heat_range')::int=2;
  select occurred_at into original_time from private.heat_activity_events where user_id=b;
  delete from public.post_votes where user_id=b;
  assert (public.get_fan_stats(a)->>'fan_credit')::int=0;
  assert (public.get_fan_stats(b)->>'heat_range')::int=0;
  insert into public.post_votes(user_id,post_id) values(b,p);
  assert (select occurred_at=original_time from private.heat_activity_events where user_id=b);
  insert into public.post_votes(user_id,post_id) values(a,p);
  assert (public.get_fan_stats(a)->>'fan_credit')::int=3; -- no self FC
  insert into public.daily_artist_votes values(b,1,current_date,now());
  update public.daily_artist_votes set artist_id=2 where user_id=b;
  assert (public.get_fan_stats(b)->>'heat_range')::int=4;
  insert into public.friendships(owner_id,friend_id,status) values(a,b,'pending');
  assert not exists(select 1 from private.heat_activity_events where source_type='friendship');
  update public.friendships set status='accepted' where owner_id=a;
  assert (public.get_fan_stats(b)->>'heat_range')::int=16;
  delete from public.friendships where owner_id=a;
  assert (public.get_fan_stats(b)->>'heat_range')::int=4;
  insert into public.comments(id,author_id,post_id) values(p,b,p);
  insert into public.comment_likes values(p,a,'like');
  assert (public.get_fan_stats(b)->>'fan_credit')::int=1;
  delete from public.comment_likes;
  assert (public.get_fan_stats(b)->>'fan_credit')::int=0;
  update public.comments set deleted_at=now();
  assert (public.get_fan_stats(b)->>'heat_range')::int=4;
  insert into public.fan_cred_events(recipient_id,source_type,source_key,points,reason)
    values(b,'moderation_adjustment','test',3,'test'),(c,'moderation_adjustment','test',1,'test');
  assert (public.get_fan_stats(a)->>'fan_rank')::int=1;
  assert (public.get_fan_stats(b)->>'fan_rank')::int=1;
  assert (public.get_fan_stats(c)->>'fan_rank')::int=3;
  assert (public.get_fan_stats(c)->>'fan_rank_total')::int=3;
  insert into private.heat_activity_events(user_id,source_type,source_key,points,occurred_at)
    select c,'post',n::text,18,'2026-01-01'::timestamptz from generate_series(1,7) n;
  r := private.heat_snapshot(c,'2026-01-01');
  assert (r->>'heat_range')::int=100 and (r->>'heat_max_count')::int=1;
  assert (private.heat_snapshot(c,'2026-01-16')->>'heat_range')::int=50;
  assert (private.heat_snapshot(c,'2026-01-31')->>'heat_days_remaining')::int=0;
  assert not has_table_privilege('authenticated','private.heat_activity_events','INSERT');
  assert not has_function_privilege('anon','public.get_fan_stats(uuid)','EXECUTE');
  assert not has_function_privilege('authenticated','private.record_heat_activity(text,jsonb,boolean,timestamptz)','EXECUTE');
end $$;
set local role authenticated;
select public.get_fan_stats('00000000-0000-4000-8000-000000000001');
reset role;
rollback;
