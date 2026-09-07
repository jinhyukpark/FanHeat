create table public.home_hero_slides (
  id bigint generated always as identity primary key,
  layout_type text not null default 'layered' check (layout_type in ('layered', 'background')),
  background_url text not null check (background_url ~ '^https?://'),
  foreground_url text check (foreground_url is null or foreground_url ~ '^https?://'),
  title text not null default '',
  subtitle text not null default '',
  active boolean not null default true,
  display_order integer not null default 0 check (display_order >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (layout_type <> 'layered' or foreground_url is not null)
);

create index home_hero_slides_active_order_idx
  on public.home_hero_slides(active, display_order, id);

alter table public.home_hero_slides enable row level security;
grant select on table public.home_hero_slides to anon, authenticated;
grant insert, update, delete on table public.home_hero_slides to authenticated;
grant usage, select on sequence public.home_hero_slides_id_seq to authenticated;

create policy "Public can view active hero slides"
  on public.home_hero_slides for select to anon using (active);
create policy "Members can view active hero slides"
  on public.home_hero_slides for select to authenticated
  using (active or (select public.is_admin()));
create policy "Admins can create hero slides"
  on public.home_hero_slides for insert to authenticated
  with check ((select public.is_admin()));
create policy "Admins can update hero slides"
  on public.home_hero_slides for update to authenticated
  using ((select public.is_admin())) with check ((select public.is_admin()));
create policy "Admins can delete hero slides"
  on public.home_hero_slides for delete to authenticated
  using ((select public.is_admin()));

create policy "Admins can upload hero images"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'fanheat-assets' and (storage.foldername(name))[1] = 'hero-slides' and (select public.is_admin()));
create policy "Admins can update hero images"
  on storage.objects for update to authenticated
  using (bucket_id = 'fanheat-assets' and (storage.foldername(name))[1] = 'hero-slides' and (select public.is_admin()))
  with check (bucket_id = 'fanheat-assets' and (storage.foldername(name))[1] = 'hero-slides' and (select public.is_admin()));
create policy "Admins can delete hero images"
  on storage.objects for delete to authenticated
  using (bucket_id = 'fanheat-assets' and (storage.foldername(name))[1] = 'hero-slides' and (select public.is_admin()));

create trigger home_hero_slides_admin_audit
  after insert or update or delete on public.home_hero_slides
  for each row execute function public.log_admin_change();

insert into public.home_hero_slides(layout_type, background_url, foreground_url, title, subtitle, display_order)
values
  ('layered', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/bg_hyuna.jpg', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/bingle_bangle.jpg', 'AOA · Bingle Bangle', 'AOA 5TH MINI ALBUM · BINGLE BANGLE', 1),
  ('layered', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/rescene-bg.jpeg', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/rescene-jacket.jpeg', 'RESCENE · Pretty Girl', '2026 SPECIAL SINGLE · PRETTY GIRL', 2),
  ('layered', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/ive-bg.jpeg', 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/ive-jacket.jpeg', 'IVE · REVIVE+', 'IVE THE 2ND ALBUM · BLACKHOLE', 3);
