update public.artist_profile_images profile_image
set display_order = profile_image.display_order + 1
where exists (
  select 1
  from public.artists artist
  where artist.id = profile_image.artist_id
    and artist.active = true
    and artist.profile_image_source_provider = 'YouTube Data API'
    and artist.image_url is not null
    and artist.image_url <> profile_image.image_url
);

insert into public.artist_profile_images (artist_id, image_url, display_order)
select artist.id, artist.image_url, 0
from public.artists artist
where artist.active = true
  and artist.profile_image_source_provider = 'YouTube Data API'
  and artist.image_url like 'https://yt3.ggpht.com/%'
on conflict (artist_id, image_url)
do update set display_order = excluded.display_order;

do $$
declare
  linked_count integer;
begin
  select count(*) into linked_count
  from public.artists artist
  where artist.active = true
    and artist.profile_image_source_provider = 'YouTube Data API'
    and exists (
      select 1
      from public.artist_profile_images profile_image
      where profile_image.artist_id = artist.id
        and profile_image.image_url = artist.image_url
        and profile_image.display_order = 0
    );

  if linked_count <> 20 then
    raise exception 'Expected 20 linked YouTube profile images, found %', linked_count;
  end if;
end
$$;
