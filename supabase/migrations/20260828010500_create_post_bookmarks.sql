create table if not exists public.post_bookmarks (
  user_id uuid not null references auth.users(id) on delete cascade,
  post_id uuid not null references public.posts(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, post_id)
);

create index if not exists post_bookmarks_post_id_idx
  on public.post_bookmarks(post_id);

alter table public.post_bookmarks enable row level security;

revoke all on table public.post_bookmarks from anon;
grant select, insert, delete on table public.post_bookmarks to authenticated;

drop policy if exists "Users can view own bookmarks" on public.post_bookmarks;
create policy "Users can view own bookmarks"
on public.post_bookmarks for select
to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "Users can add own bookmarks" on public.post_bookmarks;
create policy "Users can add own bookmarks"
on public.post_bookmarks for insert
to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete own bookmarks" on public.post_bookmarks;
create policy "Users can delete own bookmarks"
on public.post_bookmarks for delete
to authenticated
using ((select auth.uid()) = user_id);
