-- LOCAL DISPOSABLE POSTGRES ONLY. Never run this fixture on a Supabase project.
create role anon;
create role authenticated;
create schema auth;
create schema private;
create function auth.uid() returns uuid language sql stable as
$$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
grant usage on schema auth to authenticated;
create table auth.users(id uuid primary key);
create table public.profiles(id uuid primary key references auth.users);
create table public.posts(id uuid primary key, author_id uuid references auth.users, status text default 'published', created_at timestamptz default now());
create table public.comments(id uuid primary key, author_id uuid references auth.users, post_id uuid references public.posts on delete cascade, deleted_at timestamptz, created_at timestamptz default now());
create table public.profile_gallery_images(id bigint primary key, user_id uuid references auth.users, object_path text, created_at timestamptz default now());
create table public.post_bookmarks(user_id uuid references auth.users, post_id uuid references public.posts on delete cascade, created_at timestamptz default now(), primary key(user_id,post_id));
create table public.post_votes(user_id uuid references auth.users, post_id uuid references public.posts on delete cascade, created_at timestamptz default now(), primary key(user_id,post_id));
create table public.daily_artist_votes(user_id uuid references auth.users, artist_id bigint, vote_date date, created_at timestamptz default now(), primary key(user_id,vote_date));
create table public.friendships(owner_id uuid references auth.users,friend_id uuid references auth.users,status text,accepted_at timestamptz,created_at timestamptz default now(),primary key(owner_id,friend_id));
create table public.comment_likes(comment_id uuid references public.comments on delete cascade,user_id uuid references auth.users,reaction text,primary key(comment_id,user_id));
