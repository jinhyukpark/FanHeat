drop policy if exists "Admins can update member profiles" on public.profiles;
drop policy if exists profiles_owner_update on public.profiles;
create policy profiles_owner_or_admin_update on public.profiles for update to authenticated using ((select auth.uid()) = id or (select public.is_admin())) with check ((select auth.uid()) = id or (select public.is_admin()));

drop policy if exists "Admins can read all artists" on public.artists;
drop policy if exists artists_public_read on public.artists;
create policy artists_visible_read on public.artists for select to public using (active or (select public.is_admin()));

drop policy if exists "Admins can manage tracks" on public.tracks;
drop policy if exists tracks_public_read on public.tracks;
create policy tracks_visible_read on public.tracks for select to public using (active or (select public.is_admin()));
create policy "Admins can create tracks" on public.tracks for insert to authenticated with check ((select public.is_admin()));
create policy "Admins can update tracks" on public.tracks for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete tracks" on public.tracks for delete to authenticated using ((select public.is_admin()));

drop policy if exists "Admins can manage awards" on public.award_entries;
drop policy if exists awards_public_read on public.award_entries;
create policy awards_visible_read on public.award_entries for select to public using (active or (select public.is_admin()));
create policy "Admins can create awards" on public.award_entries for insert to authenticated with check ((select public.is_admin()));
create policy "Admins can update awards" on public.award_entries for update to authenticated using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete awards" on public.award_entries for delete to authenticated using ((select public.is_admin()));

drop policy if exists "Admins can read all posts" on public.posts;
drop policy if exists "Admins can update all posts" on public.posts;
drop policy if exists "Admins can delete all posts" on public.posts;
drop policy if exists posts_public_or_owner_read on public.posts;
drop policy if exists posts_owner_update on public.posts;
drop policy if exists posts_owner_delete on public.posts;
create policy posts_visible_read on public.posts for select to public using (status = 'published' or (select auth.uid()) = author_id or (select public.is_admin()));
create policy posts_owner_or_admin_update on public.posts for update to authenticated using ((select auth.uid()) = author_id or (select public.is_admin())) with check ((select auth.uid()) = author_id or (select public.is_admin()));
create policy posts_owner_or_admin_delete on public.posts for delete to authenticated using ((select auth.uid()) = author_id or (select public.is_admin()));

drop policy if exists "Admins can read all comments" on public.comments;
drop policy if exists "Admins can update all comments" on public.comments;
drop policy if exists "Admins can delete all comments" on public.comments;
drop policy if exists comments_public_read on public.comments;
drop policy if exists comments_owner_update on public.comments;
drop policy if exists comments_owner_delete on public.comments;
create policy comments_visible_read on public.comments for select to public using (deleted_at is null or (select public.is_admin()));
create policy comments_owner_or_admin_update on public.comments for update to authenticated using ((select auth.uid()) = author_id or (select public.is_admin())) with check ((select auth.uid()) = author_id or (select public.is_admin()));
create policy comments_owner_or_admin_delete on public.comments for delete to authenticated using ((select auth.uid()) = author_id or (select public.is_admin()));

drop policy if exists "Admins can read fan photo submissions" on public.fan_photo_submissions;
drop policy if exists fan_photo_submissions_select_own on public.fan_photo_submissions;
create policy fan_photo_submissions_owner_or_admin_read on public.fan_photo_submissions for select to authenticated using ((select auth.uid()) = submitter_id or (select public.is_admin()));

drop policy if exists "Admins can read fan photo submission images" on public.fan_photo_submission_images;
drop policy if exists fan_photo_submission_images_select_own on public.fan_photo_submission_images;
create policy fan_photo_submission_images_owner_or_admin_read on public.fan_photo_submission_images for select to authenticated using ((select public.is_admin()) or exists (select 1 from public.fan_photo_submissions submission where submission.id = submission_id and submission.submitter_id = (select auth.uid())));
