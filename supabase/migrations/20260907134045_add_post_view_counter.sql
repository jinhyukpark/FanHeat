create or replace function public.record_post_view(p_post_id uuid)
returns bigint
language sql
security definer
set search_path = ''
as $$
  update public.posts
  set view_count = coalesce(view_count, 0) + 1
  where id = p_post_id
    and status = 'published'
  returning view_count;
$$;

revoke all on function public.record_post_view(uuid) from public;
grant execute on function public.record_post_view(uuid) to anon, authenticated;
