create or replace function public.is_admin()
returns boolean language sql stable set search_path = ''
as $$ select coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', false) $$;

revoke all on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated;

create table if not exists public.admin_audit_logs (
  id bigint generated always as identity primary key,
  admin_user_id uuid not null references auth.users(id) on delete restrict,
  action text not null,
  entity_type text not null,
  entity_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists admin_audit_logs_created_idx on public.admin_audit_logs(created_at desc);
create index if not exists admin_audit_logs_admin_idx on public.admin_audit_logs(admin_user_id, created_at desc);
alter table public.admin_audit_logs enable row level security;
revoke all on table public.admin_audit_logs from anon;
grant select, insert on table public.admin_audit_logs to authenticated;
grant usage, select on sequence public.admin_audit_logs_id_seq to authenticated;
create policy "Admins can read audit logs" on public.admin_audit_logs for select to authenticated using ((select public.is_admin()));
create policy "Admins can create audit logs" on public.admin_audit_logs for insert to authenticated with check ((select public.is_admin()) and admin_user_id = (select auth.uid()));

create or replace function public.log_admin_change()
returns trigger language plpgsql set search_path = '' as $$
declare row_data jsonb;
begin
  if not public.is_admin() then return coalesce(new, old); end if;
  row_data := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  insert into public.admin_audit_logs(admin_user_id, action, entity_type, entity_id, details)
  values (auth.uid(), lower(tg_op), tg_table_name, row_data ->> 'id', jsonb_build_object('status', row_data ->> 'status', 'display_name', row_data ->> 'display_name', 'title', row_data ->> 'title'));
  return coalesce(new, old);
end;
$$;
revoke all on function public.log_admin_change() from public, anon, authenticated;

grant select, update on table public.profiles to authenticated;
grant select, insert, update, delete on table public.artists to authenticated;
grant select, insert, update, delete on table public.tracks to authenticated;
grant select, insert, update, delete on table public.award_entries to authenticated;
grant select, update, delete on table public.posts to authenticated;
grant select, update, delete on table public.comments to authenticated;
grant select, update on table public.fan_photo_submissions to authenticated;
grant select on table public.fan_photo_submission_images to authenticated;

create policy "Admins can update member profiles" on public.profiles for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can read all artists" on public.artists for select to authenticated using ((select public.is_admin()));
create policy "Admins can create artists" on public.artists for insert to authenticated with check ((select public.is_admin()));
create policy "Admins can update artists" on public.artists for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete artists" on public.artists for delete to authenticated using ((select public.is_admin()));
create policy "Admins can manage tracks" on public.tracks for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can manage awards" on public.award_entries for all to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can read all posts" on public.posts for select to authenticated using ((select public.is_admin()));
create policy "Admins can update all posts" on public.posts for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete all posts" on public.posts for delete to authenticated using ((select public.is_admin()));
create policy "Admins can read all comments" on public.comments for select to authenticated using ((select public.is_admin()));
create policy "Admins can update all comments" on public.comments for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete all comments" on public.comments for delete to authenticated using ((select public.is_admin()));
create policy "Admins can read fan photo submissions" on public.fan_photo_submissions for select to authenticated using ((select public.is_admin()));
create policy "Admins can review fan photo submissions" on public.fan_photo_submissions for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can read fan photo submission images" on public.fan_photo_submission_images for select to authenticated using ((select public.is_admin()));
create policy "Admins can view submitted fan photos" on storage.objects for select to authenticated using (bucket_id = 'fan-photo-submissions' and (select public.is_admin()));
create policy "Admins can delete submitted fan photos" on storage.objects for delete to authenticated using (bucket_id = 'fan-photo-submissions' and (select public.is_admin()));

create trigger profiles_admin_audit after update on public.profiles for each row execute function public.log_admin_change();
create trigger artists_admin_audit after insert or update or delete on public.artists for each row execute function public.log_admin_change();
create trigger posts_admin_audit after update or delete on public.posts for each row execute function public.log_admin_change();
create trigger comments_admin_audit after update or delete on public.comments for each row execute function public.log_admin_change();
create trigger fan_photo_submissions_admin_audit after update on public.fan_photo_submissions for each row execute function public.log_admin_change();
