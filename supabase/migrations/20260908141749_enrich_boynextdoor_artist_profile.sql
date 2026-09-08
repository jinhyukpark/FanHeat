update public.artists
set name='BOYNEXTDOOR',
    name_ko='보이넥스트도어',
    description='성호, 리우, 명재현, 태산, 이한, 운학으로 구성된 KOZ Entertainment의 6인조 보이 그룹입니다.',
    real_name='성호 · 리우 · 명재현 · 태산 · 이한 · 운학',
    role_description='K-POP 보이 그룹',
    debut_text='2023-05-30',
    agency='KOZ Entertainment',
    fandom_name='ONEDOOR (원도어)',
    hero_image_url='https://upload.wikimedia.org/wikipedia/commons/1/17/BoyNextDoor_Knock_On_Vol.1_Tour_%2820250325%29.jpg',
    bio_paragraphs=array[
      'BOYNEXTDOOR는 성호, 리우, 명재현, 태산, 이한, 운학으로 구성된 KOZ Entertainment의 6인조 보이 그룹입니다. 2023년 5월 30일 싱글 앨범 《WHO!》로 데뷔했습니다.',
      '팀명에는 또래 친구들이 공감할 수 있는 일상의 이야기를 솔직한 음악으로 표현하고, 편안하게 다가가겠다는 의미가 담겨 있습니다. 공식 팬덤명은 ONEDOOR(원도어)입니다.'
    ],
    history_items=jsonb_build_array(
      jsonb_build_object('year','2023','text','싱글 앨범 《WHO!》로 데뷔하고 EP 《WHY..》를 발표.','source_url','https://boynextdoor-official.jp/Discography'),
      jsonb_build_object('year','2024','text','두 번째 EP 《HOW?》와 세 번째 EP 《19.99》를 발표.','source_url','https://boynextdoor-official.jp/Discography'),
      jsonb_build_object('year','2025','text','네 번째 EP 《No Genre》와 다섯 번째 EP 《The Action》을 발표.','source_url','https://boynextdoor-official.jp/Discography'),
      jsonb_build_object('year','2026','text','첫 정규 앨범 《HOME》을 발표.','source_url','https://boynextdoor-official.jp/Discography/2ff48946df6e')
    ),
    instagram_url='https://www.instagram.com/boynextdoor_official/',
    x_url='https://twitter.com/BOYNEXTDOOR_KOZ',
    facebook_url='https://www.facebook.com/BOYNEXTDOOR.official',
    updated_at=now()
where slug='boynextdoor-q118178306';

with artist as (select id from public.artists where slug='boynextdoor-q118178306'),
albums(title,release_date,album_type,track_count,external_url,display_order) as (
  values
    ('WHO!','2023-05-30'::date,'Single',3,'https://boynextdoor-official.jp/Discography/1',1),
    ('WHY..','2023-09-04'::date,'EP',6,'https://boynextdoor-official.jp/Discography/4f77567f1b43',2),
    ('HOW?','2024-04-15'::date,'EP',7,'https://boynextdoor-official.jp/Discography/39834593a15c',3),
    ('19.99','2024-09-09'::date,'EP',7,'https://boynextdoor-official.jp/Discography/df20d487e30b',4),
    ('No Genre','2025-05-13'::date,'EP',7,'https://boynextdoor-official.jp/Discography/e8f1e51094c3',5),
    ('The Action','2025-10-20'::date,'EP',5,'https://boynextdoor-official.jp/Discography/e1896dc09d57',6),
    ('HOME','2026-06-08'::date,'Studio Album',9,'https://boynextdoor-official.jp/Discography/2ff48946df6e',7)
)
insert into public.artist_albums(artist_id,title,release_date,album_type,track_count,external_url,label,genre,active,display_order)
select artist.id,albums.title,albums.release_date,albums.album_type,albums.track_count,albums.external_url,'KOZ Entertainment','K-POP',false,albums.display_order
from artist cross join albums
where not exists(select 1 from public.artist_albums existing where existing.artist_id=artist.id and existing.title=albums.title);

with artist as (select id from public.artists where slug='boynextdoor-q118178306'),
tracks(album_title,track_number,title) as (
  values
    ('WHO!',1,'But I Like You'),('WHO!',2,'One and Only'),('WHO!',3,'Serenade'),
    ('WHY..',1,'But I Like You'),('WHY..',2,'One and Only'),('WHY..',3,'Serenade'),('WHY..',4,'Crying'),('WHY..',5,'But Sometimes'),('WHY..',6,'ABCDLOVE'),
    ('HOW?',1,'OUR'),('HOW?',2,'Amnesia'),('HOW?',3,'So let''s go see the stars'),('HOW?',4,'Earth, Wind & Fire'),('HOW?',5,'l i f e i s c o o l'),('HOW?',6,'Dear. My Darling'),('HOW?',7,'Earth, Wind & Fire (English Ver.)'),
    ('19.99',1,'Dangerous'),('19.99',2,'Gonna Be A Rock'),('19.99',3,'SKIT'),('19.99',4,'Nice Guy'),('19.99',5,'20'),('19.99',6,'Call Me'),('19.99',7,'Nice Guy (English Ver.)'),
    ('No Genre',1,'123-78'),('No Genre',2,'I Feel Good'),('No Genre',3,'Step By Step'),('No Genre',4,'Is That True?'),('No Genre',5,'Next Mistake'),('No Genre',6,'IF I SAY, I LOVE YOU'),('No Genre',7,'I Feel Good (English Ver.)'),
    ('The Action',1,'Live In Paris'),('The Action',2,'Hollywood Action'),('The Action',3,'JAM!'),('The Action',4,'Bathroom'),('The Action',5,'As Time Goes By'),
    ('HOME',1,'06070'),('HOME',2,'VIRAL'),('HOME',3,'ddok ddok ddok'),('HOME',4,'ADIOS!'),('HOME',5,'Upside Down'),('HOME',6,'DIVE'),('HOME',7,'Forever You'),('HOME',8,'I Wonder'),('HOME',9,'I Wonder, Always (CD Only)')
)
insert into public.artist_album_tracks(album_id,track_number,title,active,display_order)
select album.id,tracks.track_number,tracks.title,false,tracks.track_number
from tracks
join artist on true
join public.artist_albums album on album.artist_id=artist.id and album.title=tracks.album_title
on conflict(album_id,track_number) do update set title=excluded.title,updated_at=now();

with artist as (select id from public.artists where slug='boynextdoor-q118178306'),
gallery(title,image_url,original_image_url,captured_on,display_order,source_page_url,creator_name,license_name,license_url,attribution_text) as (
  values
    ('Music Bank 2024','https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/BoyNextDoor_at_Music_Bank%2C_2024_%2820240426%29.jpg/1280px-BoyNextDoor_at_Music_Bank%2C_2024_%2820240426%29.jpg','https://upload.wikimedia.org/wikipedia/commons/e/ea/BoyNextDoor_at_Music_Bank%2C_2024_%2820240426%29.jpg','2024-04-26'::date,1,'https://commons.wikimedia.org/wiki/File:BoyNextDoor_at_Music_Bank,_2024_(20240426).jpg','tenasia (티비텐)','CC BY 3.0','https://creativecommons.org/licenses/by/3.0','tenasia (티비텐) · CC BY 3.0 · Wikimedia Commons'),
    ('KNOCK ON Vol.1 Manila 2025','https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/BoyNextDoor_Knock_On_Vol.1_Tour_%2820250325%29.jpg/1280px-BoyNextDoor_Knock_On_Vol.1_Tour_%2820250325%29.jpg','https://upload.wikimedia.org/wikipedia/commons/1/17/BoyNextDoor_Knock_On_Vol.1_Tour_%2820250325%29.jpg','2025-03-22'::date,2,'https://commons.wikimedia.org/wiki/File:BoyNextDoor_Knock_On_Vol.1_Tour_(20250325).jpg','TofuMuncher','CC0 1.0','https://creativecommons.org/publicdomain/zero/1.0/','TofuMuncher · CC0 1.0 · Wikimedia Commons')
)
insert into public.artist_gallery_items(artist_id,title,image_url,original_image_url,captured_on,active,display_order,source_page_url,source_provider,creator_name,license_name,license_url,attribution_text,rights_verified_at,ai_decision,ai_reason,ai_confidence,ai_category,ai_people_visible,ai_promotional_layout,review_status,reviewed_at,source_collected_at)
select artist.id,gallery.title,gallery.image_url,gallery.original_image_url,gallery.captured_on,true,gallery.display_order,gallery.source_page_url,'wikimedia_commons',gallery.creator_name,gallery.license_name,gallery.license_url,gallery.attribution_text,now(),'photo_candidate','Wikimedia Commons의 재사용 허용 라이선스와 아티스트 단체 사진을 확인함',1,'activity_photo',true,false,'approved',now(),now()
from artist cross join gallery
where not exists(select 1 from public.artist_gallery_items existing where existing.artist_id=artist.id and existing.original_image_url=gallery.original_image_url);

do $$
declare v_artist_id bigint; album_total integer; track_total integer; gallery_total integer;
begin
  select id into v_artist_id from public.artists where slug='boynextdoor-q118178306';
  select count(*) into album_total from public.artist_albums where artist_id=v_artist_id;
  select count(*) into track_total from public.artist_album_tracks where album_id in(select id from public.artist_albums where artist_id=v_artist_id);
  select count(*) into gallery_total from public.artist_gallery_items where artist_id=v_artist_id and active;
  if album_total < 7 or track_total < 44 or gallery_total < 2 then
    raise exception 'BOYNEXTDOOR enrichment incomplete: albums %, tracks %, gallery %',album_total,track_total,gallery_total;
  end if;
end $$;
