create table public.artist_click_events (
  artist_id bigint not null references public.artists(id) on delete cascade,
  visitor_key uuid not null,
  clicked_on date not null default ((now() at time zone 'Asia/Seoul')::date),
  clicked_at timestamptz not null default now(),
  primary key (artist_id, visitor_key, clicked_on)
);

create index artist_click_events_period_idx
  on public.artist_click_events(clicked_at desc, artist_id);

alter table public.artist_click_events enable row level security;
revoke all on table public.artist_click_events from public, anon, authenticated;

create or replace function public.record_artist_click(p_artist_id bigint, p_visitor_key uuid)
returns void
language sql
security definer
set search_path = ''
as $$
  insert into public.artist_click_events (artist_id, visitor_key)
  select id, p_visitor_key
  from public.artists
  where id = p_artist_id and active = true
  on conflict (artist_id, visitor_key, clicked_on)
  do update set clicked_at = excluded.clicked_at;
$$;

revoke all on function public.record_artist_click(bigint, uuid) from public;
grant execute on function public.record_artist_click(bigint, uuid) to anon, authenticated;

create or replace function public.get_artist_activity_rankings(p_period text)
returns table (
  artist_id bigint,
  click_count bigint,
  fan_growth bigint,
  gallery_growth bigint,
  ranking_score bigint,
  rank bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_since timestamptz;
begin
  v_since := case p_period
    when 'today' then date_trunc('day', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
    when 'week' then date_trunc('week', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
    when 'month' then date_trunc('month', now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul'
    else null
  end;

  if v_since is null then
    raise exception 'Unsupported ranking period';
  end if;

  return query
  with metrics as (
    select
      a.id as artist_id,
      count(distinct (clicks.visitor_key, clicks.clicked_on))::bigint as click_count,
      count(distinct fans.id)::bigint as fan_growth,
      count(distinct gallery.id)::bigint as gallery_growth
    from public.artists a
    left join public.artist_click_events clicks
      on clicks.artist_id = a.id and clicks.clicked_at >= v_since
    left join public.artist_fans fans
      on fans.artist_id = a.id and fans.active = true and fans.created_at >= v_since
    left join public.artist_gallery_items gallery
      on gallery.artist_id = a.id
      and gallery.active = true
      and gallery.review_status = 'approved'
      and gallery.created_at >= v_since
    where a.active = true
    group by a.id
  ), scored as (
    select metrics.*, (click_count + fan_growth * 3 + gallery_growth * 2)::bigint as ranking_score
    from metrics
  ), ranked as (
    select scored.*, rank() over (order by ranking_score desc) as rank
    from scored
  )
  select ranked.artist_id, ranked.click_count, ranked.fan_growth, ranked.gallery_growth, ranked.ranking_score, ranked.rank
  from ranked
  order by ranked.ranking_score desc, ranked.click_count desc, ranked.fan_growth desc, ranked.gallery_growth desc, ranked.artist_id
  limit 50;
end;
$$;

revoke all on function public.get_artist_activity_rankings(text) from public;
grant execute on function public.get_artist_activity_rankings(text) to anon, authenticated;
