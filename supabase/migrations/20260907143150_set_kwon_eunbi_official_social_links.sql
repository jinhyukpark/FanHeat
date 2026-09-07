-- RBW official notice: https://weverse.io/kwoneunbi/notice/36672?hl=ko
update public.artists
set facebook_url = 'https://www.facebook.com/kwoneunbi.offcl/',
    x_url = 'https://x.com/kwoneunbi_offcl',
    instagram_url = 'https://www.instagram.com/kwoneunbi.official/',
    updated_at = now()
where slug = 'kwon-eun-bi-q56505060'
  and name_ko = '권은비';

do $$
begin
  if not exists (
    select 1
    from public.artists
    where slug = 'kwon-eun-bi-q56505060'
      and name_ko = '권은비'
      and facebook_url = 'https://www.facebook.com/kwoneunbi.offcl/'
      and x_url = 'https://x.com/kwoneunbi_offcl'
      and instagram_url = 'https://www.instagram.com/kwoneunbi.official/'
  ) then
    raise exception 'Kwon Eun-bi official social links were not updated';
  end if;
end
$$;
