do $$
declare
  nmixx_id bigint;
begin
  select id into nmixx_id
  from public.artists
  where slug = 'nmixx-q109307762';

  if nmixx_id is null then
    raise exception 'NMIXX artist row nmixx-q109307762 was not found';
  end if;

  update public.artists
  set
    description = '서로 다른 장르를 한 곡 안에서 결합하는 MIXX POP을 중심으로 활동하는 대한민국의 6인조 걸 그룹.',
    real_name = 'NMIXX (엔믹스)',
    role_description = '가수 · K-pop 걸 그룹',
    debut_text = '2022년 2월 22일',
    agency = 'JYP Entertainment · SQU4D',
    fandom_name = 'NSWER',
    bio_paragraphs = array[
      'NMIXX(엔믹스)는 JYP Entertainment의 레이블 SQU4D 소속 6인조 걸 그룹으로, 릴리·해원·설윤·배이·지우·규진으로 구성되어 있습니다. 2022년 2월 22일 싱글 《AD MARE》로 데뷔했습니다.',
      '팀명은 새로운 시대를 뜻하는 N과 조합·다양성을 상징하는 MIX를 결합한 이름입니다. 두 가지 이상의 장르를 한 곡 안에서 전개하는 MIXX POP을 음악적 정체성으로 삼아 보컬, 퍼포먼스와 장르 전환을 함께 선보이고 있습니다.'
    ],
    history_items = jsonb_build_array(
      jsonb_build_object(
        'year', '2022',
        'text', '2월 22일 데뷔 싱글 《AD MARE》와 타이틀곡 ‘O.O’를 발표하며 활동을 시작.',
        'source_url', 'https://nmixx.jype.com/discography/514qe3en?AmSeq=undefined&PgIndex=undefined'
      ),
      jsonb_build_object(
        'year', '2023',
        'text', '첫 미니 앨범 《expérgo》와 싱글 3집 《A Midsummer NMIXX’s Dream》을 발표.',
        'source_url', 'https://nmixx.jype.com/discography?AmSeq=1&PgIndex=2'
      ),
      jsonb_build_object(
        'year', '2024',
        'text', '《Fe3O4: BREAK》와 《Fe3O4: STICK OUT》으로 Fe3O4 시리즈를 전개.',
        'source_url', 'https://nmixx.jype.com/notice/3p3vvp6q'
      ),
      jsonb_build_object(
        'year', '2025',
        'text', '《Fe3O4: FORWARD》와 정규 앨범 《Blue Valentine》을 발표하며 디스코그래피를 확장.',
        'source_url', 'https://nmixx.jype.com/discography?AmSeq=1&PgIndex=1'
      ),
      jsonb_build_object(
        'year', '2026',
        'text', '5번째 EP 《Heavy Serenade》를 발표하고 국내외 활동을 이어감.',
        'source_url', 'https://nmixx.jype.com/notice'
      )
    ),
    award_items = jsonb_build_array(
      jsonb_build_object(
        'year', '2022',
        'text', 'Asia Artist Awards 가수 부문 이모티브상·뉴웨이브상 수상.',
        'source_url', 'https://www.asiaartistawards.com/winner/w_2022.html'
      ),
      jsonb_build_object(
        'year', '2023',
        'text', 'Asia Artist Awards 가수 부문 아이콘상·베스트초이스상 수상.',
        'source_url', 'https://www.asiaartistawards.com/winner/2023'
      )
    ),
    updated_at = now()
  where id = nmixx_id;

  insert into public.artist_gallery_items (
    artist_id, title, image_url, original_image_url, source_page_url,
    source_collected_at, source_provider, creator_name, license_name,
    license_url, attribution_text, rights_verified_at, captured_on,
    active, display_order, ai_decision, ai_reason, ai_confidence,
    ai_category, ai_people_visible, ai_promotional_layout,
    review_status, reviewed_at
  )
  select
    nmixx_id,
    'NMIXX 프랑크푸르트 공연 · ' || photo.file_number,
    'https://commons.wikimedia.org/wiki/Special:Redirect/file/Nmixx%20in%20Frankfurt%2020260324%20%28' || photo.file_number || '%29.jpg',
    'https://commons.wikimedia.org/wiki/Special:Redirect/file/Nmixx%20in%20Frankfurt%2020260324%20%28' || photo.file_number || '%29.jpg',
    'https://commons.wikimedia.org/wiki/File:Nmixx_in_Frankfurt_20260324_%28' || photo.file_number || '%29.jpg',
    now(),
    'wikimedia_commons',
    'PFNKa',
    'CC BY 4.0',
    'https://creativecommons.org/licenses/by/4.0/',
    'Photo: PFNKa · CC BY 4.0 · Wikimedia Commons',
    now(),
    date '2026-03-24',
    true,
    coalesce((select max(display_order) from public.artist_gallery_items where artist_id = nmixx_id), 0) + photo.file_number,
    'photo_candidate',
    'Wikimedia Commons에서 저작자 본인이 CC BY 4.0으로 공개한 NMIXX 공연 사진.',
    1,
    'performance',
    true,
    false,
    'approved',
    now()
  from (values (1), (2), (3), (4), (5)) as photo(file_number)
  where not exists (
    select 1
    from public.artist_gallery_items existing
    where existing.artist_id = nmixx_id
      and existing.source_page_url = 'https://commons.wikimedia.org/wiki/File:Nmixx_in_Frankfurt_20260324_%28' || photo.file_number || '%29.jpg'
  );
end
$$;
