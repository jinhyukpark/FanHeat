create policy "Admins can upload artist profile images"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'fanheat-assets'
    and (storage.foldername(name))[1] = 'artist-profiles'
    and (select public.is_admin())
  );

create policy "Admins can view artist profile image objects"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'fanheat-assets'
    and (storage.foldername(name))[1] = 'artist-profiles'
    and (select public.is_admin())
  );

create policy "Admins can delete artist profile images"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'fanheat-assets'
    and (storage.foldername(name))[1] = 'artist-profiles'
    and (select public.is_admin())
  );
