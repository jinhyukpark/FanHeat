-- Seed the prototype artist content requested for admin/user-flow testing.
-- Every insert is idempotent so the migration can be replayed safely.

do $$
declare
  asset_base constant text := 'https://yuiemljibxeoifupvluc.supabase.co/storage/v1/object/public/fanheat-assets/3207765e-4d0a-4c9c-b620-46a805ca0ee7/system/';
begin
  update public.artists
  set
    real_name = coalesce(nullif(real_name, ''), coalesce(name_ko, name)),
    role_description = coalesce(nullif(role_description, ''), 'K-POP 아티스트'),
    debut_text = coalesce(nullif(debut_text, ''), '공식 프로필 확인'),
    agency = coalesce(nullif(agency, ''), '소속사 정보'),
    fandom_name = coalesce(nullif(fandom_name, ''), 'FAN HEAT'),
    hero_image_url = coalesce(nullif(hero_image_url, ''), image_url),
    description = coalesce(nullif(description, ''), coalesce(name_ko, name) || '의 음악과 활동을 소개합니다.'),
    bio_paragraphs = case when cardinality(bio_paragraphs) = 0 then array[
      coalesce(name_ko, name) || '은(는) 음악과 무대를 통해 팬들과 꾸준히 만나고 있습니다.',
      '앨범, 공연, 팬 활동과 갤러리 콘텐츠를 FAN HEAT에서 확인할 수 있습니다.'
    ] else bio_paragraphs end,
    history_items = case when jsonb_array_length(history_items) = 0 then jsonb_build_array(
      jsonb_build_object('year', '2026', 'text', 'FAN HEAT 아티스트 페이지 공개'),
      jsonb_build_object('year', '2025', 'text', '글로벌 팬 프로젝트 참여'),
      jsonb_build_object('year', '2024', 'text', '주요 음악 활동 진행')
    ) else history_items end,
    award_items = case when jsonb_array_length(award_items) = 0 then jsonb_build_array(
      jsonb_build_object('year', '2025', 'text', '올해의 아티스트'),
      jsonb_build_object('year', '2024', 'text', '글로벌 팬 초이스'),
      jsonb_build_object('year', '2023', 'text', '디지털 음원 본상')
    ) else award_items end,
    follower_count = case when follower_count = 0 then 10000 + id * 6531 else follower_count end,
    visitor_today = case when visitor_today = 0 then 120 + id * 37 else visitor_today end,
    visitor_total = case when visitor_total = 0 then 150000 + id * 18431 else visitor_total end,
    updated_at = now();

  update public.artists set
    real_name = '아이유 (이지은)', role_description = '싱어송라이터 · 배우',
    debut_text = '2008년 9월 18일', agency = 'EDAM 엔터테인먼트', fandom_name = 'UAENA',
    description = '섬세한 감성과 폭넓은 음악 세계를 보여주는 싱어송라이터이자 배우입니다.',
    bio_paragraphs = array[
      '아이유는 섬세한 감성과 폭넓은 음악적 스펙트럼으로 사랑받는 싱어송라이터입니다.',
      '음악뿐 아니라 연기와 다양한 창작 활동을 통해 자신만의 이야기를 꾸준히 전하고 있습니다.'
    ]
  where slug = 'iu';

  update public.artists set real_name = '워너원 (Wanna One)', role_description = '보이 그룹', debut_text = '2017년 8월 7일', agency = 'Swing 엔터테인먼트', fandom_name = 'WANNABLE' where slug = 'wanna-one';
  update public.artists set real_name = 'BIGBANG', role_description = '보이 그룹', debut_text = '2006년 8월 19일', agency = 'YG 엔터테인먼트', fandom_name = 'V.I.P' where slug = 'bigbang';
  update public.artists set real_name = 'SISTAR', role_description = '걸 그룹', debut_text = '2010년 6월 3일', agency = 'Starship 엔터테인먼트', fandom_name = 'STAR1' where slug = 'sistar';
  update public.artists set real_name = 'TWICE', role_description = '걸 그룹', debut_text = '2015년 10월 20일', agency = 'JYP 엔터테인먼트', fandom_name = 'ONCE' where slug = 'twice';
  update public.artists set real_name = 'Red Velvet', role_description = '걸 그룹', debut_text = '2014년 8월 1일', agency = 'SM 엔터테인먼트', fandom_name = 'ReVeluv' where slug = 'red-velvet';
  update public.artists set real_name = 'EXO', role_description = '보이 그룹', debut_text = '2012년 4월 8일', agency = 'SM 엔터테인먼트', fandom_name = 'EXO-L' where slug = 'exo';
  update public.artists set real_name = 'BLACKPINK', role_description = '걸 그룹', debut_text = '2016년 8월 8일', agency = 'YG 엔터테인먼트', fandom_name = 'BLINK' where slug = 'blackpink';

  insert into public.artist_albums
    (artist_id, title, lead_track, release_date, album_type, track_count, cover_url, description, label, genre, active, display_order)
  select a.id, d.title, d.lead_track, d.release_date, d.album_type, d.track_count,
    asset_base || d.cover_file,
    d.title || ' 앨범의 테스트용 상세 정보입니다.', 'FAN HEAT DEMO', 'K-POP', true, d.display_order
  from public.artists a
  cross join (values
    ('꽃갈피 둘','잠 못 드는 밤 비는 내리고','2017-09-22'::date,'싱글/EP',6,'rescene-jacket.jpeg',1),
    ('Palette','팔레트 (Feat. G-DRAGON)','2017-04-21'::date,'정규앨범',10,'ive-jacket.jpeg',2),
    ('사랑이 잘','사랑이 잘 (With 오혁)','2017-04-07'::date,'싱글/EP',1,'bingle_bangle.jpg',3),
    ('밤편지','밤편지','2017-03-24'::date,'싱글/EP',1,'mypage.jpg',4),
    ('CHAT-SHIRE','스물셋','2015-10-23'::date,'미니앨범',7,'rescene-bg.jpeg',5),
    ('마음','마음','2015-05-18'::date,'디지털 싱글',2,'ive-bg.jpeg',6),
    ('소격동','소격동','2014-10-02'::date,'싱글/EP',1,'post2.jpg',7),
    ('애타는 마음','애타는 마음','2014-06-30'::date,'싱글/EP',2,'mypage_bg.jpg',8),
    ('꽃갈피','나의 옛날이야기','2014-05-16'::date,'리메이크 앨범',7,'rescene-jacket.jpeg',9),
    ('Modern Times – Epilogue','금요일에 만나요','2013-12-20'::date,'정규앨범',15,'ive-jacket.jpeg',10),
    ('Modern Times','분홍신','2013-10-08'::date,'정규앨범',13,'bingle_bangle.jpg',11),
    ('스무 살의 봄','하루 끝','2012-05-11'::date,'싱글/EP',3,'mypage.jpg',12),
    ('Last Fantasy','너랑 나','2011-11-29'::date,'정규앨범',13,'rescene-bg.jpeg',13),
    ('Real+','나만 몰랐던 이야기','2011-02-17'::date,'싱글/EP',3,'ive-bg.jpeg',14),
    ('Real','좋은 날','2010-12-09'::date,'미니앨범',6,'post2.jpg',15),
    ('IU...IM','마쉬멜로우','2009-11-12'::date,'미니앨범',7,'mypage_bg.jpg',16),
    ('Growing Up','Boo','2009-04-23'::date,'정규앨범',16,'rescene-jacket.jpeg',17),
    ('Lost and Found','미아','2008-09-23'::date,'미니앨범',6,'ive-jacket.jpeg',18)
  ) as d(title,lead_track,release_date,album_type,track_count,cover_file,display_order)
  where a.slug = 'iu'
    and not exists (select 1 from public.artist_albums x where x.artist_id = a.id and x.title = d.title);

  insert into public.artist_albums
    (artist_id, title, lead_track, release_date, album_type, track_count, cover_url, description, label, genre, active, display_order)
  select a.id, coalesce(a.name_ko,a.name) || ' 대표곡 컬렉션', coalesce(a.name_ko,a.name) || ' 대표곡 1',
    '2025-01-01'::date, '테스트 컬렉션', 5, a.image_url,
    '관리자 앨범·트랙 관리 기능을 확인하기 위한 테스트 앨범입니다.', 'FAN HEAT DEMO', 'K-POP', true, 1
  from public.artists a
  where a.slug <> 'iu'
    and not exists (select 1 from public.artist_albums x where x.artist_id = a.id and x.title = coalesce(a.name_ko,a.name) || ' 대표곡 컬렉션');

  insert into public.artist_album_tracks
    (album_id, track_number, title, duration_text, lyrics_excerpt, active, display_order)
  select album.id, 1, album.lead_track, '03:30', '관리자에서 곡 소개와 가사를 수정할 수 있는 테스트 데이터입니다.', true, 1
  from public.artist_albums album
  where album.artist_id = (select id from public.artists where slug = 'iu')
    and not exists (select 1 from public.artist_album_tracks t where t.album_id = album.id and t.track_number = 1);

  insert into public.artist_album_tracks
    (album_id, track_number, title, duration_text, lyrics_excerpt, active, display_order)
  select album.id, n, coalesce(a.name_ko,a.name) || ' 대표곡 ' || n, '03:' || lpad((20 + n * 5)::text, 2, '0'),
    '관리자에서 곡 정보와 가사를 수정할 수 있는 테스트 데이터입니다.', true, n
  from public.artists a
  join public.artist_albums album on album.artist_id = a.id and album.title = coalesce(a.name_ko,a.name) || ' 대표곡 컬렉션'
  cross join generate_series(1,5) n
  where not exists (select 1 from public.artist_album_tracks t where t.album_id = album.id and t.track_number = n);

  with known(slug, track_number, title) as (values
    ('wanna-one',1,'에너제틱'),('wanna-one',2,'Beautiful'),('wanna-one',3,'봄바람'),('wanna-one',4,'BOOMERANG'),('wanna-one',5,'켜줘'),
    ('bigbang',1,'거짓말'),('bigbang',2,'하루하루'),('bigbang',3,'FANTASTIC BABY'),('bigbang',4,'뱅뱅뱅'),('bigbang',5,'봄여름가을겨울'),
    ('sistar',1,'Touch My Body'),('sistar',2,'SHAKE IT'),('sistar',3,'Loving U'),('sistar',4,'나 혼자'),('sistar',5,'I Swear'),
    ('twice',1,'CHEER UP'),('twice',2,'TT'),('twice',3,'What is Love?'),('twice',4,'FANCY'),('twice',5,'Feel Special'),
    ('red-velvet',1,'빨간 맛'),('red-velvet',2,'Psycho'),('red-velvet',3,'Bad Boy'),('red-velvet',4,'Feel My Rhythm'),('red-velvet',5,'Queendom'),
    ('exo',1,'으르렁'),('exo',2,'CALL ME BABY'),('exo',3,'Love Shot'),('exo',4,'Tempo'),('exo',5,'첫 눈'),
    ('blackpink',1,'DDU-DU DDU-DU'),('blackpink',2,'Kill This Love'),('blackpink',3,'How You Like That'),('blackpink',4,'Pink Venom'),('blackpink',5,'Shut Down')
  )
  update public.artist_album_tracks t set title = known.title
  from known
  join public.artists a on a.slug = known.slug
  join public.artist_albums album on album.artist_id = a.id and album.title = coalesce(a.name_ko,a.name) || ' 대표곡 컬렉션'
  where t.album_id = album.id and t.track_number = known.track_number;

  insert into public.artist_fans
    (artist_id, display_name, handle, avatar_url, heat_percent, featured_rank, active, display_order)
  select a.id, f.display_name, f.handle, asset_base || f.avatar_file, f.heat_percent, f.featured_rank, true, f.display_order
  from public.artists a
  cross join (values
    ('채원','@chaewon_fh','mypage.jpg',96,1,1),('현우','@hyunwoo_star','chart1.jpg',94,2,2),
    ('민서','@minseo_luv','post2.jpg',92,3,3),('하린','@harin_day','chart7_2.jpg',78,4,4),
    ('지우','@jiwoo_wave','ive-jacket.jpeg',72,5,5),('서준','@seojun_02','chart11.jpg',68,6,6),
    ('유나','@yuna_archive','rescene-jacket.jpeg',62,7,7),('도윤','@doyoon_fan','chart3.jpg',57,8,8),
    ('수아','@sua_cloud','bingle_bangle.jpg',52,9,9),('예준','@yejun_heat','chart9.jpg',46,10,10),
    ('나은','@naeun_note','mypage_bg.jpg',39,11,11),('시우','@siwoo_music','chart6.jpg',32,12,12)
  ) as f(display_name,handle,avatar_file,heat_percent,featured_rank,display_order)
  where not exists (select 1 from public.artist_fans x where x.artist_id = a.id and x.handle = f.handle);

  insert into public.artist_gallery_items
    (artist_id, title, image_url, captured_on, active, display_order)
  select a.id, g.title,
    case g.display_order when 1 then a.image_url when 2 then asset_base || 'post_list2.jpg' else asset_base || 'post_list3.jpg' end,
    g.captured_on, true, g.display_order
  from public.artists a
  cross join (values
    ('무대 위 빛나는 순간','2026-08-24'::date,1),
    ('공연 비하인드','2026-08-18'::date,2),
    ('팬들과 함께한 하루','2026-08-09'::date,3)
  ) as g(title,captured_on,display_order)
  where not exists (select 1 from public.artist_gallery_items x where x.artist_id = a.id and x.title = g.title);
end $$;
