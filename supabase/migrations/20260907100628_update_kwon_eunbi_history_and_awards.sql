do $$
declare
  updated_count integer;
begin
  update public.artists
  set
    history_items = jsonb_build_array(
      jsonb_build_object(
        'year', '2018',
        'text', 'Mnet 《프로듀스 48》 최종 7위로 IZ*ONE 데뷔조에 합류.',
        'source_url', 'https://v.daum.net/v/gXV6aIgvDy'
      ),
      jsonb_build_object(
        'year', '2021',
        'text', 'IZ*ONE 활동 종료 후 미니 1집 《OPEN》으로 솔로 데뷔.',
        'source_url', 'https://www.yna.co.kr/amp/view/AKR20210824157600005'
      ),
      jsonb_build_object(
        'year', '2022',
        'text', '《Color》의 ‘Glitch’와 《Lethality》의 ‘Underwater’를 발표.',
        'source_url', 'https://sports.donga.com/ent/article/all/20221014/115949475/1'
      ),
      jsonb_build_object(
        'year', '2023',
        'text', '워터밤 무대를 계기로 ‘Underwater’가 역주행하며 주목받음.',
        'source_url', 'https://www.hankyung.com/article/202307039489H'
      ),
      jsonb_build_object(
        'year', '2024',
        'text', '싱글 2집 《SABOTAGE》를 발표하고 솔로 활동을 이어감.',
        'source_url', 'https://weverse.io/kwoneunbi/notice/20325?hl=ko'
      )
    ),
    award_items = jsonb_build_array(
      jsonb_build_object(
        'year', '2021',
        'text', '아시아 아티스트 어워즈 가수 부문 이모티브상.',
        'source_url', 'https://www.asiaartistawards.com/artist/detail/616/aaa/3?page=23'
      ),
      jsonb_build_object(
        'year', '2023',
        'text', 'SBS M 《더 쇼》 ‘The Flash’로 솔로 첫 음악방송 1위.',
        'source_url', 'https://www.starnewskorea.com/stview.php?no=2024070214404823276'
      ),
      jsonb_build_object(
        'year', '2023',
        'text', '아시아 아티스트 어워즈 베스트 뮤지션상.',
        'source_url', 'https://www.asiaartistawards.com/news/detail/72944/all'
      ),
      jsonb_build_object(
        'year', '2024',
        'text', 'MTN 방송광고 페스티벌 CF스타상 신인상.',
        'source_url', 'https://mice.mtn.co.kr/notice/5902c0a5-5b8d-4143-add2-2d84ec33f0f8'
      )
    ),
    updated_at = now()
  where slug = 'kwon-eun-bi-q56505060'
    and name_ko = '권은비';

  get diagnostics updated_count = row_count;
  if updated_count <> 1 then
    raise exception 'Expected to update exactly one Kwon Eun-bi artist row, updated %', updated_count;
  end if;
end
$$;
