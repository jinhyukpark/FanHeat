insert into public.home_hero_slides (
  layout_type,
  background_url,
  foreground_url,
  title,
  subtitle,
  active,
  display_order
)
select seed.layout_type,
       seed.background_url,
       seed.foreground_url,
       seed.title,
       seed.subtitle,
       true,
       seed.display_order
from (
  values
    (
      'layered',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/bg_hyuna.jpg',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/bingle_bangle.jpg',
      'AOA · Bingle Bangle',
      'AOA 5TH MINI ALBUM · BINGLE BANGLE',
      1
    ),
    (
      'layered',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/rescene-bg.jpeg',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/rescene-jacket.jpeg',
      'RESCENE · Pretty Girl',
      '2026 SPECIAL SINGLE · PRETTY GIRL',
      2
    ),
    (
      'layered',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/ive-bg.jpeg',
      'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/ive-jacket.jpeg',
      'IVE · REVIVE+',
      'IVE THE 2ND ALBUM · BLACKHOLE',
      3
    )
) as seed(layout_type, background_url, foreground_url, title, subtitle, display_order)
where not exists (select 1 from public.home_hero_slides);
